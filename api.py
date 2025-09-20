import os, io, json, uuid, base64, mimetypes, traceback, time
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote

import requests
from PIL import Image
import replicate

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

# ========================
# -------- ENV -----------
# ========================
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL   = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

LOG_FILE            = os.getenv("LOG_FILE", "user_logs.jsonl")
STATIC_DIR          = os.getenv("STATIC_DIR", "public")
UPLOADS_DIR         = os.path.join(STATIC_DIR, "uploads")
ALLOWED_ORIGINS     = os.getenv("ALLOWED_ORIGINS", "*")
PUBLIC_BASE_URL     = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# Branding
CREATOR_NAME        = os.getenv("CREATOR_NAME", "Dhruv Patel")
ASSISTANT_NAME      = os.getenv("ASSISTANT_NAME", "Droxion")
POWERED_BY_LINE     = os.getenv("POWERED_BY_LINE", "— Powered by Droxion")

# --- Image Remix Suite (Replicate) ---
REPLICATE_API_TOKEN     = os.getenv("REPLICATE_API_TOKEN", "")

# You may provide owner/model in *_MODEL and, optionally, a VERSION in the *_VERSION envs.
# If VERSION is set, we'll call "owner/model:VERSION"; otherwise just "owner/model".
REPLICATE_REMIX_MODEL   = os.getenv("REPLICATE_REMIX_MODEL",   "stability-ai/sdxl")
REPLICATE_REMIX_VERSION = os.getenv("REPLICATE_REMIX_VERSION", "")

REPLICATE_INPAINT_MODEL   = os.getenv("REPLICATE_INPAINT_MODEL",   "lucataco/sdxl-inpainting")
REPLICATE_INPAINT_VERSION = os.getenv("REPLICATE_INPAINT_VERSION", "")

REPLICATE_RMBG_MODEL    = os.getenv("REPLICATE_RMBG_MODEL",    "jianfch/stable-diffusion-rembg")
REPLICATE_RMBG_VERSION  = os.getenv("REPLICATE_RMBG_VERSION",  "")

REPLICATE_BGGEN_MODEL   = os.getenv("REPLICATE_BGGEN_MODEL",   "stability-ai/sdxl")
REPLICATE_BGGEN_VERSION = os.getenv("REPLICATE_BGGEN_VERSION", "")

replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN) if REPLICATE_API_TOKEN else None

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/public")
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}}, supports_credentials=False)

# ========================
# ------ Helpers ---------
# ========================

def _json_error(msg: str, status: int = 400):
    return jsonify({"ok": False, "error": msg}), status

def _safe_str(x) -> str:
    try:
        return str(x)
    except Exception:
        return "<unprintable>"

def _log_line(payload: dict):
    payload = dict(payload or {})
    payload["ts"] = datetime.utcnow().isoformat()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _abs_url(u: str) -> str:
    if not u: return u
    if u.startswith("http://") or u.startswith("https://"): return u
    base = PUBLIC_BASE_URL or (request.host_url.rstrip("/") if request else "")
    return urljoin(base + "/", u.lstrip("/"))

# ---- Image helpers ----
def _b64_to_pil(b64_str: str) -> Image.Image:
    data = (b64_str or "").split(",")[-1]
    return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")

def _img_to_bytes(img: Image.Image, mode="PNG") -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format=mode)
    buf.seek(0)
    return buf

def _safe_image_models_ready() -> bool:
    return bool(replicate_client)

def _spec(model: str, version: str = "") -> str:
    """Return 'owner/model:version' only if a version was provided."""
    model = (model or "").strip()
    version = (version or "").strip()
    if not model:
        return model
    return f"{model}:{version}" if version else model

def _to_urls(rep_out):
    """
    Replicate responses can be: string URL, FileOutput, or list of those.
    Always return a list of string URLs so Flask can JSON-encode them.
    """
    if rep_out is None:
        return []
    items = rep_out if isinstance(rep_out, list) else [rep_out]
    urls = []
    for x in items:
        if not x:
            continue
        try:
            s = str(x)  # FileOutput -> "https://..."
        except Exception:
            continue
        if s:
            urls.append(s)
    # de-dup while preserving order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return uniq

# ========================
# ------- Minimal Chat ----
# ========================
def _openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return prompt
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        sys = (f"You are {ASSISTANT_NAME}, created by {CREATOR_NAME}. "
               f"Be concise. End answers with '{POWERED_BY_LINE}'.")
        body = {
            "model": OPENAI_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": sys},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5
        }
        r = requests.post(url, headers=headers, json=body, timeout=60); r.raise_for_status()
        j = r.json()
        return (j["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        _log_line({"openai_error": _safe_str(e)})
        return f"{prompt}\n\n{POWERED_BY_LINE}"

# ========================
# -------- Routes --------
# ========================

@app.get("/")
def root():
    # quick diagnostics about model envs
    diag = {
        "REPLICATE_API_TOKEN_set": bool(REPLICATE_API_TOKEN),
        "remix_model_env": REPLICATE_REMIX_MODEL,
        "remix_version_env": REPLICATE_REMIX_VERSION,
        "inpaint_model_env": REPLICATE_INPAINT_MODEL,
        "inpaint_version_env": REPLICATE_INPAINT_VERSION,
        "rmbg_model_env": REPLICATE_RMBG_MODEL,
        "bggen_model_env": REPLICATE_BGGEN_MODEL,
    }
    return jsonify({"ok": True, "service": f"{ASSISTANT_NAME} API", "diag": diag, "time": datetime.utcnow().isoformat()})

@app.post("/chat")
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")
        reply = _openai_chat(prompt)
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"chat failed: {_safe_str(e)}", 500)

# ---------- Unified Image Endpoint ----------
@app.post("/imagine")
def imagine():
    """
    Text → image, image → image (remix), or inpaint (image + mask).
    Body JSON:
      prompt (required)
      image_base64 (optional)
      mask_base64 (optional)  # if present => inpaint
      style_strength (optional float 0..1, remix only)
    """
    try:
        if not _safe_image_models_ready():
            return _json_error("REPLICATE_API_TOKEN not set", 500)

        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        img_b64  = (data.get("image_base64") or "").strip()
        mask_b64 = (data.get("mask_base64") or "").strip()
        style_strength = float(data.get("style_strength") or 0.6)

        # CASE A: text-only => txt2img (use BGGEN model for generic generation)
        if not img_b64:
            out = replicate_client.run(
                _spec(REPLICATE_BGGEN_MODEL, REPLICATE_BGGEN_VERSION),
                input={"prompt": prompt, "num_inference_steps": 28, "guidance_scale": 7}
            )
            images = _to_urls(out)
            if not images:
                return _json_error("No image produced (txt2img)", 500)
            return jsonify({"ok": True, "mode": "txt2img", "images": images})

        base_img = _b64_to_pil(img_b64)
        base_bytes = _img_to_bytes(base_img, "PNG")

        # CASE B: image + mask => inpaint
        if mask_b64:
            mask_img = _b64_to_pil(mask_b64).convert("L")
            if mask_img.size != base_img.size:
                mask_img = mask_img.resize(base_img.size, Image.LANCZOS)
            mask_bytes = _img_to_bytes(mask_img, "PNG")

            out = replicate_client.run(
                _spec(REPLICATE_INPAINT_MODEL, REPLICATE_INPAINT_VERSION),
                input={
                    "image": base_bytes,
                    "mask": mask_bytes,
                    "prompt": prompt,
                    "num_inference_steps": 35,
                    "guidance_scale": 7
                }
            )
            images = _to_urls(out)
            if not images:
                return _json_error("No image produced (inpaint)", 500)
            return jsonify({"ok": True, "mode": "inpaint", "images": images})

        # CASE C: image only + prompt => remix (img2img)
        out = replicate_client.run(
            _spec(REPLICATE_REMIX_MODEL, REPLICATE_REMIX_VERSION),
            input={
                "prompt": prompt,
                "image": base_bytes,
                "num_inference_steps": 28,
                "guidance_scale": 7,
                # some SDXL variants use "strength" for img2img remixing
                "strength": style_strength
            }
        )
        images = _to_urls(out)
        if not images:
            return _json_error("No image produced (remix)", 500)
        return jsonify({"ok": True, "mode": "remix", "images": images})

    except Exception as e:
        traceback.print_exc()
        return _json_error(f"imagine failed: {_safe_str(e)}", 500)

# --- Dedicated “Remix” (face/style-lock-ish) ---
@app.post("/remix-image")
def remix_image():
    try:
        if not _safe_image_models_ready():
            return _json_error("REPLICATE_API_TOKEN not set", 500)

        data = request.get_json(force=True, silent=True) or {}
        b64 = (data.get("image_base64") or "").strip()
        prompt = (data.get("prompt") or "").strip()
        style_strength = float(data.get("style_strength") or 0.6)
        if not b64:    return _json_error("No image provided.")
        if not prompt: return _json_error("Please add a prompt.")

        img = _b64_to_pil(b64)
        img_bytes = _img_to_bytes(img, "PNG")

        out = replicate_client.run(
            _spec(REPLICATE_REMIX_MODEL, REPLICATE_REMIX_VERSION),
            input={
                "prompt": prompt,
                "image": img_bytes,
                "guidance_scale": 7,
                "num_inference_steps": 28,
                "strength": style_strength
            }
        )
        images = _to_urls(out)
        if not images:
            return _json_error("No image produced. Try a different prompt.")
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"Remix failed: {_safe_str(e)}", 500)

# --- Dedicated “Inpaint” (mask editing) ---
@app.post("/inpaint-image")
def inpaint_image():
    try:
        if not _safe_image_models_ready():
            return _json_error("REPLICATE_API_TOKEN not set", 500)

        data = request.get_json(force=True, silent=True) or {}
        base_b64 = (data.get("image_base64") or "").strip()
        mask_b64 = (data.get("mask_base64") or "").strip()
        prompt   = (data.get("prompt") or "").strip()
        if not base_b64: return _json_error("No base image.")
        if not mask_b64: return _json_error("No mask image.")
        if not prompt:   return _json_error("Please add a prompt.")

        base_img = _b64_to_pil(base_b64).convert("RGBA")
        mask_img = _b64_to_pil(mask_b64).convert("L")
        if mask_img.size != base_img.size:
            mask_img = mask_img.resize(base_img.size, Image.LANCZOS)

        base_bytes = _img_to_bytes(base_img, "PNG")
        mask_bytes = _img_to_bytes(mask_img, "PNG")

        out = replicate_client.run(
            _spec(REPLICATE_INPAINT_MODEL, REPLICATE_INPAINT_VERSION),
            input={
                "image": base_bytes,
                "mask": mask_bytes,
                "prompt": prompt,
                "num_inference_steps": 35,
                "guidance_scale": 7
            }
        )
        images = _to_urls(out)
        if not images:
            return _json_error("No image produced. Refine the mask or prompt.")
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"Inpaint failed: {_safe_str(e)}", 500)

# --- Background swap (remove BG then generate new scene) ---
@app.post("/bg-swap")
def bg_swap():
    try:
        if not _safe_image_models_ready():
            return _json_error("REPLICATE_API_TOKEN not set", 500)

        data = request.get_json(force=True, silent=True) or {}
        b64 = (data.get("image_base64") or "").strip()
        prompt = (data.get("prompt") or "").strip() or "subject on a clean studio background"
        if not b64:
            return _json_error("No image provided.")

        img = _b64_to_pil(b64)
        img_bytes = _img_to_bytes(img, "PNG")

        # 1) Remove background (most RMBG models accept a file-like image)
        cutout = replicate_client.run(
            _spec(REPLICATE_RMBG_MODEL, REPLICATE_RMBG_VERSION),
            input={"image": img_bytes}
        )
        cut_urls = _to_urls(cutout)
        if not cut_urls:
            return _json_error("Background removal failed.")
        cut_url = cut_urls[0]

        # 2) Compose into new scene
        out = replicate_client.run(
            _spec(REPLICATE_BGGEN_MODEL, REPLICATE_BGGEN_VERSION),
            input={
                "prompt": prompt,
                "image": cut_url,          # URL from step 1
                "strength": 0.65,
                "num_inference_steps": 28,
                "guidance_scale": 7
            }
        )
        images = _to_urls(out)
        if not images:
            return _json_error("No image produced. Try another prompt.")
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"BG swap failed: {_safe_str(e)}", 500)

# ---------- Static ----------
@app.get("/public/<path:filename>")
def public_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# ================
# ---- Main ------
# ================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)