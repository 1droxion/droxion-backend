from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
from datetime import datetime, timedelta
from dateutil import parser  # ✅ Fix timezone-aware parsing

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
])

LOG_FILE = "user_logs.json"

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip().lower()
        video_mode = data.get("videoMode", False)
        voice_mode = data.get("voiceMode", False)

        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        if "tarak mehta video" in prompt or "youtube" in prompt:
            return jsonify({
                "reply": '<iframe width="100%" height="315" src="https://www.youtube.com/embed/tgbNymZ7vqY" frameborder="0" allowfullscreen></iframe>',
                "videoMode": video_mode,
                "voiceMode": voice_mode
            })

        if "car image" in prompt or "image create" in prompt:
            return jsonify({
                "reply": '<img src="https://source.unsplash.com/600x400/?car" alt="Car Image" />',
                "videoMode": video_mode,
                "voiceMode": voice_mode
            })

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }

        messages = [
            {
                "role": "system",
                "content": "You are an AI assistant created by Dhruv Patel and powered by Droxion™. If someone asks 'who made you', reply with that."
            },
            {"role": "user", "content": prompt}
        ]

        payload = {
            "model": "gpt-4",
            "messages": messages
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]

        return jsonify({
            "reply": reply,
            "videoMode": video_mode,
            "voiceMode": voice_mode
        })
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

@app.route("/analyze-image", methods=["POST"])
def analyze_image():
    try:
        image = request.files.get("image")
        prompt = request.form.get("prompt", "What's in this image?").strip()
        if not image:
            return jsonify({"reply": "❌ No image uploaded."}), 400

        image_base64 = base64.b64encode(image.read()).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }

        messages = [
            {"role": "system", "content": "You are a helpful AI that can understand images and describe them."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]

        payload = {
            "model": "gpt-4-vision-preview",
            "messages": messages,
            "max_tokens": 500
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Vision error: {str(e)}"}), 500

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        prompt = request.json.get("prompt", "").strip()
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
                "width": 768,
                "height": 768,
                "num_inference_steps": 30,
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False
            }
        }

        create = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        prediction = create.json()
        get_url = prediction.get("urls", {}).get("get")

        while True:
            poll = requests.get(get_url, headers=headers)
            poll_result = poll.json()
            if poll_result.get("status") == "succeeded":
                return jsonify({"image_url": poll_result.get("output")})
            elif poll_result.get("status") == "failed":
                return jsonify({"error": "Prediction failed"}), 500
            time.sleep(1)
    except Exception as e:
        return jsonify({"error": f"Image generation error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": prompt,
            "type": "video",
            "maxResults": 1,
            "key": os.getenv("YOUTUBE_API_KEY")
        }

        res = requests.get(url, params=params)
        data = res.json()

        if "items" not in data or not data["items"]:
            return jsonify({"error": "No results found."}), 404

        item = data["items"][0]
        return jsonify({
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        })
    except Exception as e:
        return jsonify({"error": f"YouTube error: {str(e)}"}), 500

@app.route("/track", methods=["POST"])
def track():
    try:
        data = request.json
        user_id = data.get("user_id")
        action = data.get("action")
        input_text = data.get("input")
        timestamp = data.get("timestamp", datetime.utcnow().isoformat())

        if not user_id or not action:
            return jsonify({"error": "Missing user_id or action."}), 400

        log = {"user_id": user_id, "action": action, "input": input_text, "timestamp": timestamp}

        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w") as f:
                json.dump([log], f, indent=2)
        else:
            with open(LOG_FILE, "r+") as f:
                logs = json.load(f)
                logs.append(log)
                f.seek(0)
                json.dump(logs, f, indent=2)

        return jsonify({"status": "logged"})
    except Exception as e:
        return jsonify({"error": f"Tracking error: {str(e)}"}), 500

@app.route("/stats", methods=["GET"])
def stats():
    try:
        if not os.path.exists(LOG_FILE):
            return jsonify({"dau": 0, "wau": 0, "mau": 0})

        with open(LOG_FILE, "r") as f:
            logs = json.load(f)

        now = datetime.utcnow()
        users_1d = set()
        users_7d = set()
        users_30d = set()

        for log in logs:
            t = parser.isoparse(log["timestamp"])  # ✅ Fix for aware timestamps
            uid = log["user_id"]
            if now - t <= timedelta(days=1):
                users_1d.add(uid)
            if now - t <= timedelta(days=7):
                users_7d.add(uid)
            if now - t <= timedelta(days=30):
                users_30d.add(uid)

        return jsonify({
            "dau": len(users_1d),
            "wau": len(users_7d),
            "mau": len(users_30d)
        })
    except Exception as e:
        return jsonify({"error": f"Stats error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
