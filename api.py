# api.py (add this route)
import os, io, base64
from flask import Flask, request, jsonify
from flask_cors import CORS
import replicate

app = Flask(__name__)
CORS(app)

# env:
# REPLICATE_API_TOKEN=xxxxxxxx
# IMG_TEXT2IMG_MODEL="black-forest-labs/flux-schnell"
# IMG_TEXT2IMG_VERSION="PUT_LATEST_VERSION_HASH_HERE"
# IMG_REPIX_MODEL="timbrooks/instruct-pix2pix"
# IMG_REPIX_VERSION="PUT_LATEST_VERSION_HASH_HERE"
# IMG_INPAINT_MODEL="stability-ai/stable-diffusion-inpainting"
# IMG_INPAINT_VERSION="PUT_LATEST_VERSION_HASH_HERE"

def _b64_to_data_url(b64_bytes, mime="image/png"):
    return f"data:{mime};base64,{base64.b64encode(b64_bytes).decode()}"

def _file_to_data_url(fs_file, mime="image/png"):
    # fs_file is werkzeug FileStorage
    content = fs_file.read()
    fs_file.seek(0)
    return _b64_to_data_url(content, mime=mime)

def _stringify_output(result):
    """
    Replicate can return: list[str URLs], list[FileOutput], single URL, etc.
    Normalize to list[str].
    """
    if result is None:
        return []
    if isinstance(result, (str,)):
        return [result]
    if isinstance(result, list):
        out = []
        for x in result:
            # FileOutput has .url or string cast
            try:
                if hasattr(x, "url"):
                    out.append(str(x.url))
                else:
                    out.append(str(x))
            except Exception:
                out.append(str(x))
        return out
    # Fallback for dict or other
    try:
        if hasattr(result, "url"):
            return [str(result.url)]
        return [str(result)]
    except Exception:
        return [repr(result)]

@app.post("/image")
def image_endpoint():
    """
    Universal image endpoint.
    Body: multipart/form-data or JSON
      mode: "text2img" | "remix" | "inpaint"
      prompt: str
      negative_prompt?: str
      image?: file (for remix/inpaint)
      mask?: file (for inpaint; white=change, black=keep)
      strength?: float (0..1) for remix
      width?, height?: ints (optional, text2img)
    """
    mode = (request.form.get("mode") or request.json.get("mode") if request.is_json else "").strip().lower()
    prompt = (request.form.get("prompt") or (request.json.get("prompt") if request.is_json else "")).strip()
    negative = (request.form.get("negative_prompt") or (request.json.get("negative_prompt") if request.is_json else "")).strip()

    if not mode:
        return jsonify({"error": "mode required"}), 400
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Optional params
    strength = float(request.form.get("strength") or (request.json.get("strength") if request.is_json else 0.6) or 0.6)
    width = int(request.form.get("width") or (request.json.get("width") if request.is_json else 768) or 768)
    height = int(request.form.get("height") or (request.json.get("height") if request.is_json else 768) or 768)

    try:
        if mode == "text2img":
            model = os.environ.get("IMG_TEXT2IMG_MODEL", "black-forest-labs/flux-schnell")
            version = os.environ.get("IMG_TEXT2IMG_VERSION", "")
            # NOTE: paste a valid version hash from Replicate into env to avoid 422.
            out = replicate.run(
                f"{model}:{version}" if version else model,
                input={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    # Some models accept negative_prompt; harmless to include if ignored
                    "negative_prompt": negative or None,
                }
            )

        elif mode == "remix":
            # Requires an image
            if "image" not in request.files:
                return jsonify({"error": "image file required for remix"}), 400
            image = request.files["image"]
            img_data_url = _file_to_data_url(image)

            model = os.environ.get("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
            version = os.environ.get("IMG_REPIX_VERSION", "")
            out = replicate.run(
                f"{model}:{version}" if version else model,
                input={
                    "image": img_data_url,
                    "prompt": prompt,
                    "num_outputs": 1,
                    "guidance_scale": 7.5,
                    "image_guidance_scale": max(0.0, min(strength, 1.0)),  # 0..1
                }
            )

        elif mode == "inpaint":
            if "image" not in request.files or "mask" not in request.files:
                return jsonify({"error": "image and mask files required for inpaint"}), 400
            image = request.files["image"]
            mask = request.files["mask"]
            img_data_url = _file_to_data_url(image)
            mask_data_url = _file_to_data_url(mask)

            model = os.environ.get("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
            version = os.environ.get("IMG_INPAINT_VERSION", "")
            out = replicate.run(
                f"{model}:{version}" if version else model,
                input={
                    "image": img_data_url,
                    "mask": mask_data_url,
                    "prompt": prompt,
                    "negative_prompt": negative or None,
                    "width": width, "height": height,
                }
            )

        else:
            return jsonify({"error": f"unknown mode '{mode}'"}), 400

        urls = _stringify_output(out)
        return jsonify({"ok": True, "outputs": urls})

    except replicate.exceptions.ReplicateError as e:
        # Typical 422 from invalid version/perms
        return jsonify({"ok": False, "error": "replicate_error", "detail": str(e)}), 422
    except Exception as e:
        return jsonify({"ok": False, "error": "server_error", "detail": str(e)}), 500