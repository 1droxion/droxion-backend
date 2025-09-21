# api.py — Droxion backend (Chat + identity-safe image tools)
# Endpoints:
#   /health
#   /chat
#   /remix-image
#   /inpaint-image
#   /remix-face-locked
#   /bg-swap
#
# Extras in this version:
# - Auto-downscale uploads to <= 1024px (prevents CUDA OOM on Replicate)
# - Flatten alpha (RGBA→RGB) so models don't choke
# - Friendly OOM message and robust error handling
# - All Replicate outputs normalized to URL strings

import os, re, io, base64
from flask import Flask, request, jsonify
from flask_cors import CORS

# Providers (installed in requirements.txt)
# openai>=1.0.0 anthropic google-generativeai replicate pillow
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate

from PIL import Image

app = Flask(__name__)
CORS(app)

# ===== ENV =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# REPLICATE_API_TOKEN must be set in env for replicate SDK to work.

# Image models (you can pin exact versions via *_VERSION hashes)
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")  # put model version hash if you want to pin

IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

# Face lock (identity-preserving). Optional.
FACE_LOCK_MODEL   = os.getenv("FACE_LOCK_MODEL", "")        # e.g. "tencentarc/instantid"
FACE_LOCK_VERSION = os.getenv("FACE_LOCK_VERSION", "")

# Face restore (optional sharpening)
FACE_RESTORE_MODEL   = os.getenv("FACE_RESTORE_MODEL", "")  # e.g. "sczhou/codeformer"
FACE_RESTORE_VERSION = os.getenv("FACE_RESTORE_VERSION", "")

# Background swap (optional)
BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")        # e.g. "cjwbw/rembg"
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")      # e.g. "black-forest-labs/flux-schnell"
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")

# ===== Clients (lazy) =====
def get_openai():
    return OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def get_anthropic():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

def get_gemini():
    if not GOOGLE_API_KEY:
        return None
    genai.configure(api_key=GOOGLE_API_KEY)
    return genai

# ===== Helpers =====
def err(status, msg, detail=None):
    out = {"ok": False, "error": msg}
    if detail:
        out["detail"] = str(detail)
    return jsonify(out), status

def require(val, name):
    if not val:
        raise ValueError(f"{name} required")

def b64_is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

def str_urls(rep_result):
    """
    Normalize Replicate outputs to List[str] of URLs.
    Handles list[str], list[FileOutput], or single object.
    """
    if rep_result is None:
        return []
    if isinstance(rep_result, list):
        out = []
        for x in rep_result:
            try:
                out.append(str(x.url) if hasattr(x, "url") else str(x))
            except Exception:
                out.append(str(x))
        return out
    try:
        return [str(rep_result.url)] if hasattr(rep_result, "url") else [str(rep_result)]
    except Exception:
        return [repr(rep_result)]

# ---- Image pre-processing: auto-resize & alpha flatten ----
DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,", re.I)

def dataurl_to_image(b64: str) -> Image.Image:
    m = DATA_URL_RE.match(b64 or "")
    if not m:
        raise ValueError("not a data URL")
    raw = base64.b64decode(b64.split(",", 1)[1])
    return Image.open(io.BytesIO(raw)).convert("RGBA")

def image_to_dataurl(img: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def ensure_png_opaque(b64: str) -> str:
    """Flatten RGBA → RGB against white; keep PNG container."""
    try:
        img = dataurl_to_image(b64)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            return image_to_dataurl(bg, fmt="PNG")
    except Exception:
        pass
    return b64

def ensure_max_size(b64_or_url: str, max_px: int = 1024) -> str:
    """
    If it's a data URL, downscale longest side to <= max_px and flatten alpha.
    If it's http(s), leave as-is (Replicate will fetch).
    """
    if not isinstance(b64_or_url, str):
        return b64_or_url
    if b64_or_url.startswith("http://") or b64_or_url.startswith("https://"):
        return b64_or_url
    if not DATA_URL_RE.match(b64_or_url):
        return b64_or_url
    img = dataurl_to_image(b64_or_url)
    w, h = img.size
    m = max(w, h)
    if m > max_px:
        scale = max_px / float(m)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    # flatten alpha
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg.convert("RGB")
    return image_to_dataurl(img, fmt="PNG")

def is_oom(e: Exception) -> bool:
    s = str(e).lower()
    return ("out of memory" in s) or ("cuda" in s and "memory" in s)

# ===== Routes =====
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "droxion",
        "chat": {
            "openai": bool(OPENAI_API_KEY),
            "anthropic": bool(ANTHROPIC_API_KEY),
            "gemini": bool(GOOGLE_API_KEY),
        }
    })

# ---- CHAT (GPT-4o → Claude 3.5 Sonnet → Gemini 1.5 Pro) ----
@app.post("/chat")
def chat():
    """
    Body:
      { "messages": [{role, content}, ...] } OR { "prompt": "..." }
    Returns:
      { ok, model, text }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages_in = data.get("messages")
        prompt = data.get("prompt")

        if not messages_in and prompt:
            messages_in = [{"role": "user", "content": prompt}]
        if not messages_in:
            return err(400, "messages or prompt required")

        # 1) GPT-4o
        try:
            oc = get_openai()
            if oc:
                resp = oc.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_in,
                    temperature=0.2
                )
                return jsonify({"ok": True, "model": "gpt-4o", "text": resp.choices[0].message.content})
        except Exception:
            pass

        # 2) Claude 3.5 Sonnet
        try:
            ac = get_anthropic()
            if ac:
                sys_prompt = ""
                convo = []
                for m in messages_in:
                    r, c = m.get("role"), m.get("content", "")
                    if r == "system":
                        sys_prompt = (sys_prompt + "\n" + c).strip()
                    elif r in ("user", "assistant"):
                        convo.append({"role": r, "content": c})
                msg = ac.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=1024,
                    temperature=0.2,
                    system=sys_prompt or None,
                    messages=convo
                )
                out = "".join([b.text for b in msg.content if hasattr(b, "text")])
                return jsonify({"ok": True, "model": "claude-3.5-sonnet", "text": out})
        except Exception:
            pass

        # 3) Gemini 1.5 Pro
        try:
            g = get_gemini()
            if g:
                model = g.GenerativeModel("gemini-1.5-pro")
                stitched = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in messages_in])
                resp = model.generate_content(stitched)
                return jsonify({"ok": True, "model": "gemini-1.5-pro", "text": getattr(resp, "text", "") or ""})
        except Exception:
            pass

        return err(502, "all providers failed (OpenAI → Anthropic → Gemini)")
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: REMIX (style remix, keeps structure) ----
@app.post("/remix-image")
def remix_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = ensure_max_size(data.get("image_base64"), 1024)
        prompt = data.get("prompt", "")
        style_strength = float(data.get("style_strength", 0.5))  # 0..1

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 7.5,
            "image_guidance_scale": max(0.0, min(style_strength, 1.0))
        })
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        if is_oom(e):
            return err(413, "Image was too large for the GPU. Try a smaller image or lower detail.", e)
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: INPAINT (mask white=change, black=keep) ----
@app.post("/inpaint-image")
def inpaint_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = ensure_max_size(data.get("image_base64"), 1024)
        mask_b64 = ensure_max_size(data.get("mask_base64"), 1024)
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(mask_b64, "mask_base64")
        require(prompt, "prompt")

        model_ref = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "mask": mask_b64 if b64_is_data_url(mask_b64) else str(mask_b64),
            "prompt": prompt
        })
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        if is_oom(e):
            return err(413, "Image/mask was too large for the GPU. Try smaller size.", e)
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: FACE-LOCKED REMIX (same person identity) ----
@app.post("/remix-face-locked")
def remix_face_locked():
    """
    JSON:
      image_base64: data:image/*;base64,...
      prompt: "pixar style portrait..." (light prompt recommended)
      id_image_base64?: optional separate reference; if missing, uses image_base64
      strength?: 0..1 (default 0.45) lower = stronger identity lock
      restore_face?: bool (default True)
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = ensure_max_size(data.get("image_base64"), 1024)
        prompt = data.get("prompt", "")
        id_b64 = ensure_max_size(data.get("id_image_base64") or img_b64, 1024)
        strength = float(data.get("strength", 0.45))
        restore_face = bool(data.get("restore_face", True))

        require(img_b64, "image_base64")

        if not FACE_LOCK_MODEL:
            return err(501, "face_lock_not_configured",
                       "Set FACE_LOCK_MODEL / FACE_LOCK_VERSION in env.")
        model_ref = f"{FACE_LOCK_MODEL}:{FACE_LOCK_VERSION}" if FACE_LOCK_VERSION else FACE_LOCK_MODEL

        gen = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "id_image": id_b64 if b64_is_data_url(id_b64) else str(id_b64),
            "prompt": prompt,
            "denoise_strength": max(0.2, min(strength, 0.8)),
            "num_outputs": 1,
            "guidance_scale": 6.5
        })
        urls = str_urls(gen)
        if not urls:
            return err(502, "no image returned from face_lock model")
        out_url = urls[0]

        if restore_face and FACE_RESTORE_MODEL:
            fr_ref = f"{FACE_RESTORE_MODEL}:{FACE_RESTORE_VERSION}" if FACE_RESTORE_VERSION else FACE_RESTORE_MODEL
            fr = replicate.run(fr_ref, input={
                "image": out_url,
                "fidelity": 0.7  # common CodeFormer-like control
            })
            fr_urls = str_urls(fr)
            if fr_urls:
                out_url = fr_urls[0]

        return jsonify({"ok": True, "images": [out_url]})
    except replicate.exceptions.ReplicateError as e:
        if is_oom(e):
            return err(413, "Image was too large for the GPU. Try a smaller image.", e)
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: BACKGROUND SWAP (subject cutout + generated BG) ----
@app.post("/bg-swap")
def bg_swap():
    """
    JSON:
      image_base64: data:image/*;base64,...
      prompt: "new background description"
    Returns:
      { ok, subject_png: [url], background: [url] }
    Compose client-side by overlaying subject_png on background.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = ensure_max_size(data.get("image_base64"), 1024)
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_REMOVE_MODEL/BG_REMOVE_VERSION & BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")
        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")

        # 1) Subject cutout
        rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        cut = replicate.run(rm_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64)
        })
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        # 2) Generate new background (slightly smaller to save VRAM/cost)
        bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(bg_ref, input={"prompt": prompt, "width": 896, "height": 896})
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")

        return jsonify({"ok": True, "subject_png": cut_urls[:1], "background": bg_urls[:1]})
    except replicate.exceptions.ReplicateError as e:
        if is_oom(e):
            return err(413, "Image was too large for the GPU. Try a smaller image.", e)
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- main ----
if __name__ == "__main__":
    # Bind to all interfaces for Render/hosted use; PORT default 8000 for local dev
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))