import os
import io
import base64
from typing import List, Union

from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image

import replicate


# ========== ENV / CONFIG ==========
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# You can provide either just "owner/model" or "owner/model:version".
# Leave VERSION empty if you want Replicate to use the model's default/latest.
REPLICATE_REMIX_MODEL   = os.getenv("REPLICATE_REMIX_MODEL",   "stability-ai/stable-diffusion-3.5-large")
REPLICATE_REMIX_VERSION = os.getenv("REPLICATE_REMIX_VERSION", "")

REPLICATE_INPAINT_MODEL   = os.getenv("REPLICATE_INPAINT_MODEL",   "lucataco/sdxl-inpainting")
REPLICATE_INPAINT_VERSION = os.getenv("REPLICATE_INPAINT_VERSION", "")

# Background removal (produces transparent PNG)
REPLICATE_RMBG_MODEL   = os.getenv("REPLICATE_RMBG_MODEL",   "jianfch/stable-diffusion-rembg")
REPLICATE_RMBG_VERSION = os.getenv("REPLICATE_RMBG_VERSION", "")

# Simple background generator (optional)
REPLICATE_BGGEN_MODEL   = os.getenv("REPLICATE_BGGEN_MODEL",   "stability-ai/sdxl")
REPLICATE_BGGEN_VERSION = os.getenv("REPLICATE_BGGEN_VERSION", "")

replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN) if REPLICATE_API_TOKEN else None


# ========== FLASK APP ==========
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)


# ========== HELPERS ==========

def _spec(model: str, version: str = "") -> str:
    """
    Return 'owner/model:version' only when version provided, otherwise 'owner/model'.
    Avoids 404/422 'invalid version' when you haven't set a version yet.
    """
    if not model:
        return ""
    model = model.strip()
    version = (version or "").strip()
    return f"{model}:{version}" if version else model


def _b64_to_pil(b64_str: str) -> Image.Image:
    """
    Accepts a data URL (data:image/...;base64,...) or raw base64 string.
    Returns a PIL Image (RGBA where possible).
    """
    if not b64_str:
        raise ValueError("Missing base64 image.")

    # strip data URL prefix if present
    if "," in b64_str and b64_str.lower().startswith("data:"):
        b64_str = b64_str.split(",", 1)[1]

    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw))
    # Keep alpha if present; otherwise convert to RGB
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    return img


def _img_to_data_url(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def _to_url_list(output: Union[str, dict, list]) -> List[str]:
    """
    Replicate output can be:
      - a URL string
      - a list of URL strings
      - a list of File objects
      - a dict with 'image'/'images'
    Normalize to list[str] of HTTPS URLs (or data URLs).
    """
    urls: List[str] = []

    def coerce_one(x):
        if x is None:
            return
        # File object (replicate.files.File or FileOutput)
        # Most have either .url or .path that is already an https URL.
        url = None
        if hasattr(x, "url") and isinstance(getattr(x, "url"), str):
            url = x.url
        elif hasattr(x, "path") and isinstance(getattr(x, "path"), str):
            url = x.path
        elif isinstance(x, str):
            url = x
        # Some models return dicts like {"image": "https://..."} or {"images": [...]}
        elif isinstance(x, dict):
            if "image" in x and isinstance(x["image"], str):
                url = x["image"]
            elif "images" in x and isinstance(x["images"], list):
                for y in x["images"]:
                    coerce_one(y)
                return
        if url:
            urls.append(url)

    if isinstance(output, list):
        for item in output:
            coerce_one(item)
    else:
        coerce_one(output)

    return urls


def _require_models_ready():
    if not replicate_client:
        raise RuntimeError("Missing REPLICATE_API_TOKEN.")
    return True


# ========== ROUTES ==========

@app.route("/", methods=["GET"])
def root():
    """Tiny health + env echo (safe)."""
    return jsonify({
        "ok": True,
        "REPLICATE_API_TOKEN_set": bool(REPLICATE_API_TOKEN),
        "remix_model_env": REPLICATE_REMIX_MODEL,
        "remix_version_env": REPLICATE_REMIX_VERSION,
        "inpaint_model_env": REPLICATE_INPAINT_MODEL,
        "inpaint_version_env": REPLICATE_INPAINT_VERSION,
        "rmbg_model_env": REPLICATE_RMBG_MODEL,
        "bggen_model_env": REPLICATE_BGGEN_MODEL,
    })


@app.route("/remix-image", methods=["POST"])
def remix_image():
    """
    Image-to-image / “remix”.
    Body: { image_base64, prompt, style_strength? (0..1) }
    """
    try:
        _require_models_ready()

        data = request.get_json(force=True, silent=False)
        image_b64 = (data or {}).get("image_base64", "")
        prompt = (data or {}).get("prompt", "") or ""
        strength = float((data or {}).get("style_strength", 0.6))  # 0..1

        # For SD3.5 the param is 'image' + 'prompt' + 'strength'
        # We can send the source image as a data URL; Replicate accepts it.
        model_id = _spec(REPLICATE_REMIX_MODEL, REPLICATE_REMIX_VERSION)
        if not model_id:
            raise RuntimeError("Remix model not configured.")

        prediction = replicate_client.predictions.create(
            model=model_id,
            input={
                "image": image_b64,
                "prompt": prompt,
                # SDXL img2img expects 'strength'; leave if model ignores
                "strength": max(0.0, min(1.0, strength)),
            },
        )

        # Wait for completion
        prediction.wait()
        if prediction.status != "succeeded":
            raise RuntimeError(f"Remix failed: {prediction.error or prediction.status}")

        images = _to_url_list(prediction.output)
        if not images:
            raise RuntimeError("No images returned from remix.")

        return jsonify({"ok": True, "images": images})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/inpaint-image", methods=["POST"])
def inpaint_image():
    """
    Inpainting with mask.
    Body: { image_base64, mask_base64, prompt }
    - White = change; Black = keep
    """
    try:
        _require_models_ready()

        data = request.get_json(force=True, silent=False)
        image_b64 = (data or {}).get("image_base64", "")
        mask_b64 = (data or {}).get("mask_base64", "")
        prompt = (data or {}).get("prompt", "") or ""

        if not image_b64:
            raise ValueError("image_base64 is required.")
        if not mask_b64:
            raise ValueError("mask_base64 is required.")

        model_id = _spec(REPLICATE_INPAINT_MODEL, REPLICATE_INPAINT_VERSION)
        if not model_id:
            raise RuntimeError("Inpaint model not configured.")

        # Many SDXL inpaint forks accept "image", "mask", "prompt"
        prediction = replicate_client.predictions.create(
            model=model_id,
            input={
                "image": image_b64,
                "mask": mask_b64,
                "prompt": prompt,
            },
        )

        prediction.wait()
        if prediction.status != "succeeded":
            raise RuntimeError(f"Inpaint failed: {prediction.error or prediction.status}")

        images = _to_url_list(prediction.output)
        if not images:
            raise RuntimeError("No images returned from inpaint.")

        return jsonify({"ok": True, "images": images})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/bg-swap", methods=["POST"])
def bg_swap():
    """
    Very simple background workflow:
      1) Remove background (transparent PNG) using rembg model.
      2) (Optional) Generate a new background image with BGGEN model using 'prompt'.
    Returns whatever the models output as URLs.
    Body: { image_base64, prompt? }
    """
    try:
        _require_models_ready()

        data = request.get_json(force=True, silent=False)
        image_b64 = (data or {}).get("image_base64", "")
        prompt = (data or {}).get("prompt", "") or ""

        if not image_b64:
            raise ValueError("image_base64 is required.")

        # Step 1: remove background
        rmbg_id = _spec(REPLICATE_RMBG_MODEL, REPLICATE_RMBG_VERSION)
        if not rmbg_id:
            raise RuntimeError("RMBG model not configured.")

        cutout_pred = replicate_client.predictions.create(
            model=rmbg_id,
            input={"image": image_b64},
        )
        cutout_pred.wait()
        if cutout_pred.status != "succeeded":
            raise RuntimeError(f"RMBG failed: {cutout_pred.error or cutout_pred.status}")

        cutout_urls = _to_url_list(cutout_pred.output)
        images = list(cutout_urls)

        # Step 2: optional background generation
        if prompt.strip():
            bg_id = _spec(REPLICATE_BGGEN_MODEL, REPLICATE_BGGEN_VERSION)
            if bg_id:
                bg_pred = replicate_client.predictions.create(
                    model=bg_id,
                    input={"prompt": prompt},
                )
                bg_pred.wait()
                if bg_pred.status == "succeeded":
                    images.extend(_to_url_list(bg_pred.output))

        if not images:
            raise RuntimeError("No images returned from background workflow.")

        return jsonify({"ok": True, "images": images})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ========== DEV SERVER ==========
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)