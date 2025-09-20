import os
import io
import base64
from typing import List

from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
import replicate

# ------------ ENV & CONFIG ------------

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# You can override these in Render’s environment.
REPLICATE_REMIX_MODEL   = os.getenv("REPLICATE_REMIX_MODEL",   "stability-ai/stable-diffusion-3.5-large")  # txt2img & img2img
REPLICATE_REMIX_VERSION = os.getenv("REPLICATE_REMIX_VERSION", "")  # optional

# Known-good inpaint model+version (you can override both via env)
REPLICATE_INPAINT_MODEL   = os.getenv("REPLICATE_INPAINT_MODEL",   "lucataco/sdxl-inpainting")
REPLICATE_INPAINT_VERSION = os.getenv(
    "REPLICATE_INPAINT_VERSION",
    # version you said you pasted in Render:
    "8d50e2f8e2841c26aeb4808e88e84f1cf5a08f2b65c0a36d6d3e5ff5d0f3fd3b"
)

# Simple background remover (demo)
REPLICATE_RMBG_MODEL    = os.getenv("REPLICATE_RMBG_MODEL",   "jianfch/stable-diffusion-rembg")
REPLICATE_RMBG_VERSION  = os.getenv("REPLICATE_RMBG_VERSION", "")

# Init client (ok if empty; we’ll fail gracefully)
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN) if REPLICATE_API_TOKEN else None

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ------------ HELPERS ------------

def _safe_models_ready() -> bool:
    return replicate_client is not None

def _b64_to_bytes(data_uri_or_b64: str) -> bytes:
    """Accepts 'data:image/png;base64,...' or raw base64."""
    if "," in data_uri_or_b64:
        data_uri_or_b64 = data_uri_or_b64.split(",", 1)[1]
    return base64.b64decode(data_uri_or_b64)

def _upload_bytes_to_replicate(buf: bytes, filename: str):
    """Upload a bytes buffer to Replicate file storage and return the handle (SDK will embed the URL)."""
    return replicate.files.upload(io.BytesIO(buf), filename=filename)

def _as_urls(output) -> List[str]:
    """
    Replicate SDK returns a list of URLs (sometimes nested).
    Normalize to a flat list[str].
    """
    if output is None:
        return []
    if isinstance(output, (list, tuple)):
        return [str(x) for x in output]
    return [str(output)]

def _model_spec(model: str, version: str) -> str:
    """Return 'owner/model:version' if version was provided and model doesn't already include a colon."""
    if not model:
        return ""
    if ":" in model:  # already pinned
        return model
    return f"{model}:{version}" if version else model

# ------------ ROUTES ------------

@app.get("/")
def root_status():
    return jsonify({
        "ok": True,
        "REPLICATE_API_TOKEN_set": bool(REPLICATE_API_TOKEN),
        "remix_model_env":   REPLICATE_REMIX_MODEL,
        "remix_version_env": REPLICATE_REMIX_VERSION,
        "inpaint_model_env": REPLICATE_INPAINT_MODEL,
        "inpaint_version_env": REPLICATE_INPAINT_VERSION,
        "rmbg_model_env":    REPLICATE_RMBG_MODEL,
        "rmbg_version_env":  REPLICATE_RMBG_VERSION,
    })

@app.get("/health")
def health():
    return jsonify({"ok": True})

# --- Remix (img2img) ---
@app.post("/remix-image")
def remix_image():
    """
    Body JSON:
    {
      "image_base64": "data:image/png;base64,...",
      "prompt": "text prompt",
      "style_strength": 0.6   # 0..1, lower = closer to original
    }
    """
    try:
        if not _safe_models_ready():
            return jsonify(ok=False, error="Replicate API token not configured"), 500

        j = request.get_json(force=True) or {}
        prompt = (j.get("prompt") or "").strip()
        image_b64 = j.get("image_base64")
        style_strength = float(j.get("style_strength", 0.6))

        if not image_b64:
            return jsonify(ok=False, error="Missing image_base64"), 400
        if not prompt:
            return jsonify(ok=False, error="Missing prompt"), 400

        img_bytes = _b64_to_bytes(image_b64)
        img_file  = _upload_bytes_to_replicate(img_bytes, "image.png")

        spec = _model_spec(REPLICATE_REMIX_MODEL, REPLICATE_REMIX_VERSION)
        pred = replicate_client.predictions.create(
            model=spec,
            input={
                # SD3.5 supports image+prompt for img2img
                "image": img_file,
                "prompt": prompt,
                # Some SD variants use 'strength', some 'guidance'; SD3.5 uses 'strength'
                "strength": max(0.0, min(style_strength, 1.0)),
            },
        )
        pred.wait()

        if pred.status != "succeeded":
            return jsonify(ok=False, error=f"Replicate remix failed: {pred.status}"), 500

        return jsonify(ok=True, images=_as_urls(pred.output))
    except replicate.exceptions.ReplicateError as e:
        return jsonify(ok=False, error=f"ReplicateError: {e}"), 500
    except Exception as e:
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 500

# --- Inpaint (mask areas to change) ---
@app.post("/inpaint-image")
def inpaint_image():
    """
    Body JSON:
    {
      "image_base64": "data:image/png;base64,...",
      "mask_base64":  "data:image/png;base64,...",  # WHITE = change, BLACK = keep
      "prompt": "remove the jacket..."
    }
    """
    try:
        if not _safe_models_ready():
            return jsonify(ok=False, error="Replicate API token not configured"), 500

        j = request.get_json(force=True) or {}
        prompt   = (j.get("prompt") or "").strip()
        image_b64 = j.get("image_base64")
        mask_b64  = j.get("mask_base64")

        if not image_b64:
            return jsonify(ok=False, error="Missing image_base64"), 400
        if not mask_b64:
            return jsonify(ok=False, error="Missing mask_base64"), 400
        if not prompt:
            return jsonify(ok=False, error="Missing prompt"), 400

        img_bytes  = _b64_to_bytes(image_b64)
        mask_bytes = _b64_to_bytes(mask_b64)

        img_file  = _upload_bytes_to_replicate(img_bytes,  "image.png")
        mask_file = _upload_bytes_to_replicate(mask_bytes, "mask.png")

        spec = _model_spec(REPLICATE_INPAINT_MODEL, REPLICATE_INPAINT_VERSION)
        pred = replicate_client.predictions.create(
            model=spec,
            input={
                "image":  img_file,
                "mask":   mask_file,
                "prompt": prompt,
                # Lower keeps identity/background stable. Adjust if needed.
                "strength": 0.5,
            },
        )
        pred.wait()

        if pred.status != "succeeded" or not pred.output:
            return jsonify(ok=False, error=f"Replicate inpaint failed: {pred.status}"), 500

        return jsonify(ok=True, images=_as_urls(pred.output))
    except replicate.exceptions.ReplicateError as e:
        return jsonify(ok=False, error=f"ReplicateError: {e}"), 500
    except Exception as e:
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 500

# --- Background remove/swap (simple) ---
@app.post("/bg-swap")
def bg_swap():
    """
    Body JSON:
    {
      "image_base64": "data:image/png;base64,...",
      "prompt": "on a beach at sunset"   # optional, depends on model
    }
    This demo just calls a rembg-style model; adapt as you like.
    """
    try:
        if not _safe_models_ready():
            return jsonify(ok=False, error="Replicate API token not configured"), 500

        j = request.get_json(force=True) or {}
        image_b64 = j.get("image_base64")
        prompt = (j.get("prompt") or "").strip()

        if not image_b64:
            return jsonify(ok=False, error="Missing image_base64"), 400

        img_bytes = _b64_to_bytes(image_b64)
        img_file  = _upload_bytes_to_replicate(img_bytes, "image.png")

        spec = _model_spec(REPLICATE_RMBG_MODEL, REPLICATE_RMBG_VERSION)
        pred = replicate_client.predictions.create(
            model=spec,
            input={
                "image": img_file,
                **({"prompt": prompt} if prompt else {})
            },
        )
        pred.wait()

        if pred.status != "succeeded" or not pred.output:
            return jsonify(ok=False, error=f"Replicate rmbg failed: {pred.status}"), 500

        return jsonify(ok=True, images=_as_urls(pred.output))
    except replicate.exceptions.ReplicateError as e:
        return jsonify(ok=False, error=f"ReplicateError: {e}"), 500
    except Exception as e:
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 500

# ------------ MAIN ------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)