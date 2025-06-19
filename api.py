from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
]}}, supports_credentials=True)

LOG_FILE = "user_logs.json"

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/chat", methods=["POST"])
@cross_origin()
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

@app.route("/generate-image", methods=["POST"])
@cross_origin()
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
@cross_origin()
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

@app.route("/logs.json", methods=["GET"])
@cross_origin()
def download_logs_json():
    token = request.args.get("token")
    if token != os.getenv("ADMIN_TOKEN", "droxion2025"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)

        days = int(request.args.get("days", 0))
        user_filter = request.args.get("user")
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            logs = [log for log in logs if parser.parse(log["timestamp"]) >= cutoff]

        if user_filter:
            logs = [log for log in logs if log["user_id"] == user_filter]

        response = make_response(json.dumps(logs, indent=2))
        response.headers["Content-Disposition"] = "attachment; filename=logs.json"
        response.headers["Content-Type"] = "application/json"
        return response
    except Exception as e:
        return jsonify({"error": f"Log export error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
