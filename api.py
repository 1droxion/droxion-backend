from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re
import sys
import logging
import time
import datetime
import json
import subprocess

# ✅ Load environment variables
load_dotenv()

# ✅ Init Flask
app = Flask(__name__)

# ✅ Allow only Droxion frontend
CORS(app, origins=[
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
], supports_credentials=True)

# ✅ Logging
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# ✅ Public folder
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

# ✅ Home route
@app.route("/")
def home():
    return "✅ Droxion API is live."


# ✅ Generate AI Image
@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        headers = {
            "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
            "Content-Type": "application/json"
        }
        payload = {
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

        create = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        if create.status_code != 201:
            return jsonify({"error": "Failed to create prediction", "details": create.json()}), 500

        prediction = create.json()
        get_url = prediction.get("urls", {}).get("get")

        while True:
            poll = requests.get(get_url, headers=headers)
            poll_result = poll.json()
            status = poll_result.get("status")
            if status == "succeeded":
                return jsonify({"image_url": poll_result.get("output")})
            if status == "failed":
                return jsonify({"error": "Prediction failed"}), 500
            time.sleep(1)

    except Exception as e:
        return jsonify({"error": f"Exception: {str(e)}"}), 500


# ✅ AI Chat route using OpenRouter
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return jsonify({"error": "Missing OpenRouter API key"}), 500

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

        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        result = response.json()

        if response.status_code != 200:
            return jsonify({"reply": f"❌ Error: {result.get('message', 'Unknown error')}"}), 400

        reply = result.get("choices", [{}])[0].get("message", {}).get("content", "No reply")
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"}), 500


# ✅ Reel Generator API
@app.route("/generate", methods=["POST"])
def generate_reel():
    try:
        config = request.get_json()

        # Map dropdown values to config values
        config_mapped = {
            "topic": config.get("topic", ""),
            "language": config.get("language", "English"),
            "voice": config.get("voice", "onyx"),
            "voiceSpeed": config.get("voiceSpeed", 1.0),
            "clipCount": int(config.get("clipCount", 10)),
            "fontSize": 80,
            "subtitleColor": "white",
            "subtitlePosition": config.get("subtitlePosition", "bottom").lower(),
            "musicVolume": config.get("musicVolume", "medium"),
            "tone": config.get("style", "cinematic").lower(),
            "lengthSec": 25 if config.get("length") == "Short" else 35 if config.get("length") == "Medium" else 45,
            "filenameMode": "auto",
            "customFilename": "",
            "manualScript": "yes" if config.get("mode") == "Manual" else "no",
            "userScript": config.get("userScript", ""),
            "captionStyle": "sentence" if config.get("captions") == "Sentence" else "word" if config.get("captions") == "Word-by-Word" else "none",
            "branding": config.get("branding", "no").lower()
        }

        with open("config.json", "w") as f:
            json.dump(config_mapped, f)

        # Run the generator
        result = subprocess.run(["python", "auto_reel_final.py"], capture_output=True, text=True)
        print("▶️ Script Output:", result.stdout)
        print("❗ Script Error:", result.stderr)

        # Find the latest mp4
        videos = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
        latest_video = max(videos, key=lambda x: os.path.getctime(os.path.join(PUBLIC_FOLDER, x)))
        return jsonify({"videoUrl": f"/{latest_video}"})

    except Exception as e:
        print("❌ Generate Error:", e)
        return jsonify({"error": str(e)}), 500


# ✅ Run
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
