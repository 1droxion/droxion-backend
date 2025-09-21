# api.py — Droxion backend (Chat + identity-safe image tools)
# - /chat: GPT-4o → Claude 3.5 Sonnet → Gemini 1.5 Pro (auto-fallbacks)
# - /remix-image: style remix (keeps structure) via Instruct-Pix2Pix (with auto-resize + OOM retry)
# - /inpaint-image: mask edits (white=change, black=keep) (with auto-resize)
# - /remix-face-locked: ID-locked remix (optional)
# - /bg-swap: subject cutout + generated background (optional)
# - All Replicate outputs become plain URLs (strings)
# - CORS enabled; helpful errors

import os, io, base64
from flask import Flask, request, jsonify
from flask_cors import CORS

# === Providers (install listed in requirements.txt) ===
# pip install: flask flask-cors openai anthropic google-generativeai replicate requests stripe pillow
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate
from replicate.exceptions import ReplicateError
from PIL import Image

app = Flask(__name__)
CORS(app)

# ===== ENV =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# REPLICATE_API_TOKEN must be set for the replicate SDK to work

# Image models (keep names EXACT + set VERSION hashes to avoid 404/422)
# NOTE: Correct owner is "timothybrooks" (not "timbrooks" or "imothybrooks")
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timothybrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")  # paste latest 64-char hash

IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

# Face lock (identity-preserving). Optional.
FACE_LOCK_MODEL   = os.getenv("FACE_LOCK_MODEL", "")
FACE_LOCK_VERSION = os.getenv("FACE_LOCK_VERSION", "")

# Face restore (sharpen only; no identity change). Optional.
FACE_RESTORE_MODEL   = os.getenv("FACE_RESTORE_MODEL", "")
FACE_RESTORE_VERSION = os.getenv("FACE_RESTORE_VERSION", "")

# Background swap (optional)
BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")
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

def _dataurl_to_bytes(data_url: str) -> bytes | None:
    if isinstance(data_url, str) and data_url.startswith("data:"):
        return base64.b64decode(data_url.split(",", 1)[1])
    return None

def _bytes_to_dataurl(img_bytes: bytes, fmt="PNG") -> str:
    mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"

def resize_data_url(data_url: str, max_side: int = 768, is_mask: bool = False) -> str:
    """
    Downscale keeping aspect. Masks use NEAREST to keep crisp edges.
    If input is not a data URL, return unchanged (Replicate accepts http(s) URLs too).
    """
    raw = _dataurl_to_bytes(data_url)
    if raw is None:
        return data_url
    im = Image.open(io.BytesIO(raw))
    if is_mask:
        if im.mode != "L":
            im = im.convert("L")
    else:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
    w, h = im.size
    scale = min(1.0, float(max_side) / max(w, h))
    if scale < 1.0:
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        im = im.resize(new_size, Image.NEAREST if is_mask else Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return _bytes_to_dataurl(buf.getvalue(), fmt="PNG")

def str_urls(rep_result):
    """
    Normalize Replicate outputs to List[str] of URLs.
    Handles list[str], list[FileOutput], single URL/object.
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

def model_ref(name: str, version: str) -> str:
    return f"{name}:{version}" if version else name

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
                return jsonify({"ok": True, "model": "gemini-1.5-pro", "text": resp.text or ""})
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
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "").strip()
        style_strength = float(data.get("style_strength", 0.45))  # 0..1

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        # auto-resize to avoid CUDA OOM
        img_b64_small = resize_data_url(img_b64, max_side=768)

        # safe ranges
        style_strength = max(0.2, min(style_strength, 0.8))
        image_guidance_scale = max(1.0, min(3.0, 1.0 + style_strength * 2.0))  # ~1.4–2.6 typical
        guidance_scale = 7.0

        mref = model_ref(IMG_REPIX_MODEL, IMG_REPIX_VERSION)

        def run_once(image_b64, igs=image_guidance_scale, gs=guidance_scale):
            return replicate.run(mref, input={
                "image": image_b64,
                "prompt": prompt,
                "num_outputs": 1,
                "guidance_scale": gs,
                "image_guidance_scale": igs
            })

        try:
            out = run_once(img_b64_small)
        except ReplicateError as e:
            msg = str(e).lower()
            # retry smaller & lighter on OOM
            if "cuda out of memory" in msg or "oom" in msg:
                img_b64_smaller = resize_data_url(img_b64, max_side=640)
                out = replicate.run(mref, input={
                    "image": img_b64_smaller,
                    "prompt": prompt,
                    "num_outputs": 1,
                    "guidance_scale": 6.0,
                    "image_guidance_scale": max(1.0, image_guidance_scale * 0.8),
                })
            else:
                raise

        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})

    except ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: INPAINT (mask white=change, black=keep) ----
@app.post("/inpaint-image")
def inpaint_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        mask_b64 = data.get("mask_base64")
        prompt = data.get("prompt", "").strip()

        require(img_b64, "image_base64")
        require(mask_b64, "mask_base64")
        require(prompt, "prompt")

        # ensure both are same resized size
        img_small = resize_data_url(img_b64, max_side=768, is_mask=False)
        mask_small = resize_data_url(mask_b64, max_side=768, is_mask=True)

        mref = model_ref(IMG_INPAINT_MODEL, IMG_INPAINT_VERSION)

        def run_once(i, m):
            return replicate.run(mref, input={"image": i, "mask": m, "prompt": prompt})

        try:
            out = run_once(img_small, mask_small)
        except ReplicateError as e:
            if "cuda out of memory" in str(e).lower():
                img_sm = resize_data_url(img_b64, max_side=640, is_mask=False)
                mask_sm = resize_data_url(mask_b64, max_side=640, is_mask=True)
                out = run_once(img_sm, mask_sm)
            else:
                raise

        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})

    except ReplicateError as e:
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
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")
        id_b64 = data.get("id_image_base64") or img_b64
        strength = float(data.get("strength", 0.45))
        restore_face = bool(data.get("restore_face", True))

        require(img_b64, "image_base64")

        if not FACE_LOCK_MODEL:
            return err(501, "face_lock_not_configured",
                       "Set FACE_LOCK_MODEL / FACE_LOCK_VERSION in env.")
        mref = model_ref(FACE_LOCK_MODEL, FACE_LOCK_VERSION)

        # Resize for stability
        i_small = resize_data_url(img_b64, max_side=768)
        id_small = resize_data_url(id_b64, max_side=768)

        gen = replicate.run(mref, input={
            "image": i_small,
            "id_image": id_small,
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
            fr_ref = model_ref(FACE_RESTORE_MODEL, FACE_RESTORE_VERSION)
            fr = replicate.run(fr_ref, input={"image": out_url, "fidelity": 0.7})
            fr_urls = str_urls(fr)
            if fr_urls:
                out_url = fr_urls[0]

        return jsonify({"ok": True, "images": [out_url]})
    except ReplicateError as e:
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
    Returns (MVP):
      { ok, subject_png: [url], background: [url] }
    Compose client-side by overlaying subject_png on background.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_REMOVE_MODEL/BG_REMOVE_VERSION & BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")
        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")

        # 1) Subject cutout (resize first)
        rm_ref = model_ref(BG_REMOVE_MODEL, BG_REMOVE_VERSION)
        cut = replicate.run(rm_ref, input={"image": resize_data_url(img_b64, max_side=768)})
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        # 2) Generate new background
        bg_ref = model_ref(BG_COMPOSE_MODEL, BG_COMPOSE_VERSION)
        bg = replicate.run(bg_ref, input={"prompt": prompt, "width": 1024, "height": 1024})
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")

        return jsonify({"ok": True, "subject_png": cut_urls[:1], "background": bg_urls[:1]})
    except ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- main ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))