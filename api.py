# api.py — Droxion backend (Flask + Replicate)
import os
import io
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
import replicate

app = Flask(__name__)
CORS(app)

# ---- Replicate client ----
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
if not REPLICATE_API_TOKEN:
    raise RuntimeError("REPLICATE_API_TOKEN missing")
rep = replicate.Client(api_token=REPLICATE_API_TOKEN)

# ---- Model IDs from env (versions optional) ----
REMIX_MODEL   = os.getenv("REPLICATE_REMIX_MODEL",   "stability-ai/stable-diffusion-3.5-large")
REMIX_VERSION = os.getenv("REPLICATE_REMIX_VERSION", "")

INPAINT_MODEL   = os.getenv("REPLICATE_INPAINT_MODEL",   "lucataco/sdxl-inpainting")
INPAINT_VERSION = os.getenv("REPLICATE_INPAINT_VERSION", "")

RMBG_MODEL   = os.getenv("REPLICATE_RMBG_MODEL",   "jianfch/stable-diffusion-rembg")
RMBG_VERSION = os.getenv("REPLICATE_RMBG_VERSION", "")


def _b64_to_bytesio(data_url: str) -> io.BytesIO:
    """Accepts 'data:image/png;base64,...' or raw base64, returns BytesIO."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return io.BytesIO(base64.b64decode(data_url))


@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "REPLICATE_API_TOKEN_set": bool(REPLICATE_API_TOKEN),
        "remix_model_env": REMIX_MODEL,
        "remix_version_env": REMIX_VERSION,
        "inpaint_model_env": INPAINT_MODEL,
        "inpaint_version_env": INPAINT_VERSION,
        "rmbg_model_env": RMBG_MODEL,
        "rmbg_version_env": RMBG_VERSION,
    })


@app.post("/remix-image")
def remix_image():
    try:
        payload = request.get_json(force=True)
        image_b64 = payload.get("image_base64")
        prompt = payload.get("prompt", "")
        style_strength = float(payload.get("style_strength", 0.6))

        if not image_b64:
            return jsonify({"ok": False, "error": "image_base64 required"}), 400

        img_io = _b64_to_bytesio(image_b64)
        model = f"{REMIX_MODEL}:{REMIX_VERSION}" if REMIX_VERSION else REMIX_MODEL

        out = rep.run(model, input={
            "image": img_io,
            "prompt": prompt,
            "strength": style_strength,  # ignored by some models; safe to include
        })

        images = out if isinstance(out, list) else [out]
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/inpaint-image")
def inpaint_image():
    try:
        payload = request.get_json(force=True)
        image_b64 = payload.get("image_base64")
        mask_b64  = payload.get("mask_base64")
        prompt = payload.get("prompt", "")

        if not image_b64 or not mask_b64:
            return jsonify({"ok": False, "error": "image_base64 and mask_base64 required"}), 400

        img_io  = _b64_to_bytesio(image_b64)
        mask_io = _b64_to_bytesio(mask_b64)
        model = f"{INPAINT_MODEL}:{INPAINT_VERSION}" if INPAINT_VERSION else INPAINT_MODEL

        out = rep.run(model, input={
            "image": img_io,
            "mask":  mask_io,
            "prompt": prompt,
        })

        images = out if isinstance(out, list) else [out]
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/bg-swap")
def bg_swap():
    """Background remove/replace. If no prompt: transparent PNG output."""
    try:
        payload = request.get_json(force=True)
        image_b64 = payload.get("image_base64")
        prompt = payload.get("prompt", "")

        if not image_b64:
            return jsonify({"ok": False, "error": "image_base64 required"}), 400

        img_io = _b64_to_bytesio(image_b64)
        model = f"{RMBG_MODEL}:{RMBG_VERSION}" if RMBG_VERSION else RMBG_MODEL

        out = rep.run(model, input={
            "image": img_io,
            "prompt": prompt or None,
        })

        images = out if isinstance(out, list) else [out]
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))