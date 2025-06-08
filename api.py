from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re
import sys
import time
import logging

# ✅ Log to stdout for Render
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Load .env
load_dotenv()

app = Flask(__name__)

# ✅ Allow only Droxion domains
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

# ✅ Create public folder
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
if not os.path.exists(PUBLIC_FOLDER):
    os.makedirs(PUBLIC_FOLDER)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ User stats
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
        auto_generates = 6

        stats = {
            "credits": 18,
            "videosThisMonth": len(videos),
            "imagesThisMonth": len(images),
            "autoGenerates": auto_generates,
            "plan": plan
        }

        return jsonify(stats)
    except Exception as e:
        print("❌ Stats Error:", e)
        return jsonify({"error": "Could not fetch stats"}), 500

# ✅ AI Image with polling and real error message
@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        print("🖼️ Prompt:", prompt)

        headers = {
            "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",  # SDXL 1.0
            "input": {
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 30,
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False
            }
        }

        create = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        prediction = create.json()

        print("📤 Created:", prediction)

        if create.status_code != 201:
            return jsonify({"error": "Replicate API failed", "details": prediction}), 500

        prediction_url = prediction.get("urls", {}).get("get")
        if not prediction_url:
            return jsonify({"error": "No polling URL"}), 500

        # Polling
        for _ in range(20):
            poll = requests.get(prediction_url, headers=headers).json()
            status = poll.get("status")

            print("🔁 Polling:", status)

            if status == "succeeded":
                url = poll.get("output", [None])[0]
                return jsonify({"url": url}) if url else jsonify({"error": "No image URL returned"}), 500

            if status in ["failed", "canceled"]:
                print("❌ Failure:", poll)
                return jsonify({
                    "error": poll.get("error") or "Generation failed. Try different prompt.",
                    "details": poll
                }), 500

            time.sleep(2)

        return jsonify({"error": "⏳ Timed out. Try again later."}), 504

    except Exception as e:
        print("❌ Exception:", str(e))
        return jsonify({"error": f"Exception: {str(e)}"}), 500

# ✅ AI Chat (OpenRouter)
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        print("📩 Chat Prompt:", prompt)

        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return jsonify({"error": "API key missing"}), 500

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are an assistant powered by Droxion."},
                {"role": "user", "content": prompt}
            ]
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        result = res.json()
        print("✅ Chat Response:", result)

        if res.status_code != 200:
            return jsonify({"reply": f"❌ Error: {result.get('message', 'Unknown')}"}), 400

        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except Exception as e:
        print("❌ Chat Error:", str(e))
        return jsonify({"reply": f"Error: {str(e)}"}), 500

# ✅ Run server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
