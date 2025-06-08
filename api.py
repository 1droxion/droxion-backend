from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re

# Load environment variables
load_dotenv()

# Initialize app
app = Flask(__name__)

# Allow frontend
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

# Public folder for user stats
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
if not os.path.exists(PUBLIC_FOLDER):
    os.makedirs(PUBLIC_FOLDER)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ USER STATS
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

# ✅ AI IMAGE GENERATOR (Replicate SDXL) with debug logs
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        print("🖼️ Image prompt:", prompt)

        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
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

        print("📦 Replicate status:", response.status_code)
        print("📤 Raw Response:", response.text)

        result = response.json()

        if response.status_code != 200:
            return jsonify({"error": result}), 500

        image_url = result.get("output", [None])[0]
        if not image_url:
            return jsonify({"error": "Image generation failed."}), 500

        return jsonify({"url": image_url})

    except Exception as e:
        print("❌ Image Generation Error:", e)
        return jsonify({"error": f"Image generation failed: {str(e)}"}), 500

# ✅ AI CHAT (OpenRouter GPT-3.5)
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        print("📩 Prompt received:", prompt)

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

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )

        print("📦 Chat status:", response.status_code)
        result = response.json()
        print("✅ Chat result:", result)

        if response.status_code != 200:
            return jsonify({"reply": f"❌ OpenRouter Error: {result.get('message', 'Unknown error')}"}), 400

        if "choices" in result and result["choices"]:
            reply = result["choices"][0]["message"]["content"]
            return jsonify({"reply": reply})
        else:
            return jsonify({"reply": "⚠️ No reply from model."})

    except Exception as e:
        print("❌ Chat Exception:", e)
        return jsonify({"reply": f"Error: {str(e)}"}), 500

# ✅ Start app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
