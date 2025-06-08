from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re
import sys
import logging
import time

# ✅ Log to stdout for Render
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
load_dotenv()

app = Flask(__name__)

# ✅ Allow Droxion frontend domains
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/user-stats", methods=["GET"])
def user_stats():
    try:
        plan = {
            "name": "Starter",
            "videoLimit": 5,
            "imageLimit": 20,
            "autoLimit": 10
        }
        videos = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
        images = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".png") and "styled" in f]
        stats = {
            "credits": 18,
            "videosThisMonth": len(videos),
            "imagesThisMonth": len(images),
            "autoGenerates": 6,
            "plan": plan
        }
        return jsonify(stats)
    except Exception as e:
        print("❌ Stats Error:", e)
        return jsonify({"error": "Could not fetch stats"}), 500

# ✅ FIXED: Generate Image (poll until ready)
@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        print("🖼️ Prompt received:", prompt)

        headers = {
            "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",  # SDXL
            "input": {
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 30,
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False
            }
        }

        # 1. Create prediction
        response = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        prediction = response.json()

        if response.status_code != 201:
            print("❌ Create Error:", prediction)
            return jsonify({"error": "Failed to create prediction", "details": prediction}), 500

        prediction_url = prediction.get("urls", {}).get("get")
        if not prediction_url:
            return jsonify({"error": "No polling URL returned"}), 500

        # 2. Poll until output is ready
        for _ in range(30):
            poll = requests.get(prediction_url, headers=headers)
            poll_data = poll.json()
            status = poll_data.get("status")

            if status == "succeeded":
                output = poll_data.get("output")
                if output and isinstance(output, list):
                    return jsonify({"url": output[0]})
                break
            elif status == "failed":
                return jsonify({"error": "Image generation failed."}), 500

            time.sleep(1)

        return jsonify({"error": "Timeout waiting for image."}), 504

    except Exception as e:
        print("❌ Generation Error:", str(e))
        return jsonify({"error": f"Exception: {str(e)}"}), 500

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        print("📩 Chat prompt:", prompt)

        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are an assistant powered by Droxion."},
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        result = response.json()

        if response.status_code != 200:
            return jsonify({"reply": f"❌ OpenRouter Error: {result.get('message', 'Unknown error')}"}), 400

        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except Exception as e:
        print("❌ Chat Error:", e)
        return jsonify({"reply": f"Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
