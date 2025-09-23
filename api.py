# api.py — Droxion Mini Image API (Replicate, prompt-only)
# - POST /generate-image {prompt} -> {image_url}
# - GET  /user-stats -> {coins}
# - Uses Replicate "model endpoint" (no hardcoded version) to avoid 404s

import os, time
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    print("⚠️  REPLICATE_API_TOKEN is not set. Set it in Render/Vercel env.")

# Choose a good default text→image model.
# You can switch to "stability-ai/sdxl" if you prefer SDXL outputs.
MODEL = os.getenv("REPLICATE_MODEL", "black-forest-labs/flux-schnell")

app = Flask(__name__)
CORS(app)

@app.get("/user-stats")
def user_stats():
    # simple stub so your UI can show coins
    return jsonify({"coins": 999})

@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Missing 'prompt'"}), 400

    # Optional knobs (UI doesn’t send these yet, but safe to accept)
    width = int(data.get("width", 1024))
    height = int(data.get("height", 1024))
    num_outputs = int(data.get("num_outputs", 1))
    guidance = float(data.get("guidance", 3.5))
    steps = int(data.get("steps", 28))
    timeout_s = int(data.get("timeout_s", 180))

    # Build a friendly, style-safe prompt
    final_prompt = prompt.strip()

    try:
        # 1) Create prediction (use model endpoint, not version hash)
        create_url = f"https://api.replicate.com/v1/models/{MODEL}/predictions"
        headers = {
            "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }

        # Inputs vary by model; these are broadly OK for FLUX/SDXL
        body = {
            "input": {
                "prompt": final_prompt,
                "width": width,
                "height": height,
                "num_outputs": num_outputs,
                "guidance": guidance,
                "num_inference_steps": steps,
            }
        }

        r = requests.post(create_url, json=body, headers=headers, timeout=30)
        if r.status_code == 404:
            # Most common cause: wrong model name
            return jsonify({
                "error": "Replicate 404 (model not found).",
                "hint": f"MODEL='{MODEL}' may be wrong or private."
            }), 502

        if r.status_code >= 400:
            return jsonify({"error": "Replicate create failed", "detail": r.text}), 502

        pred = r.json()
        pred_id = pred.get("id")
        status = pred.get("status", "starting")

        # 2) Poll until completed / failed
        poll_url = pred.get("urls", {}).get("get")
        start = time.time()
        while status not in ("succeeded", "failed", "canceled"):
            if time.time() - start > timeout_s:
                return jsonify({"error": "Generation timed out"}), 504
            time.sleep(1.0)
            pr = requests.get(poll_url, headers=headers, timeout=20)
            if pr.status_code >= 400:
                return jsonify({"error": "Replicate poll failed", "detail": pr.text}), 502
            pj = pr.json()
            status = pj.get("status")
            pred = pj

        if status != "succeeded":
            return jsonify({"error": f"Generation {status}", "detail": pred}), 502

        output = pred.get("output") or []
        if isinstance(output, list) and output:
            image_url = output[0]
        elif isinstance(output, str):
            image_url = output
        else:
            return jsonify({"error": "No image URL in output", "detail": pred}), 502

        return jsonify({"image_url": image_url})

    except requests.RequestException as e:
        return jsonify({"error": "Network error calling Replicate", "detail": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Server error", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))