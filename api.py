from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re

load_dotenv()

app = Flask(__name__)

# ✅ Allow Droxion frontends
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",  # ✅ Stable SDXL
                "input": {
                    "prompt": prompt,
                    "width": 1024,
                    "height": 1024,
                    "num_inference_steps": 30,
                    "refine": "expert_ensemble_refiner",
                    "apply_watermark": False
                }
            }
        )
        result = response.json()
        image_url = result["output"][0]
        return jsonify({"url": image_url})

    except Exception as e:
        print("❌ Image Generation Error:", e)
        return jsonify({"error": "Image generation failed."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
