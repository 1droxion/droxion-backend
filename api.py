from flask import Flask, request, jsonify, render_template_string, make_response
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
from collections import Counter
from dateutil import parser
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://www.droxion.com", "http://localhost:5173"]}})

LOG_FILE = "user_logs.json"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response

@app.route("/")
def home():
    return "\u2705 Droxion API is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "\u2757 Prompt is required."}), 400

        headers = {
            "Authorization": f"Bearer {os.getenv('ROUTER_KEY')}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are Droxion AI Assistant."},
                {"role": "user", "content": prompt}
            ]
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_data = res.json()

        if "choices" not in response_data:
            return jsonify({"reply": f"\u274C OpenAI error: {response_data}"}), 500

        reply = response_data["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"\u274C Error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "")
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": prompt,
            "type": "video",
            "maxResults": 1,
            "key": os.getenv("YOUTUBE_API_KEY")
        }
        res = requests.get(url, params=params).json()
        item = res["items"][0]
        video_id = item["id"]["videoId"]
        return jsonify({
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })
    except Exception as e:
        return jsonify({"error": f"YouTube error: {str(e)}"}), 500

@app.route("/style-photo", methods=["POST"])
def style_photo():
    try:
        image_file = request.files.get("image")
        prompt = request.form.get("prompt", "")
        style = request.form.get("style", "Pixar")

        if not image_file or not prompt:
            return jsonify({"error": "Missing image or prompt"}), 400

        upload = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": os.getenv("IMGBB_API_KEY")},
            files={"image": image_file}
        ).json()

        image_url = upload["data"]["url"]

        headers = {
            "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "8ef2637dcd8b451b7f6f12e423d5a551d13a6501503681c60236e2c1825f3d10",
            "input": {
                "image": image_url,
                "prompt": f"{prompt}, {style}"
            }
        }

        response = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload).json()

        poll_url = response["urls"]["get"]
        while True:
            poll = requests.get(poll_url, headers=headers).json()
            if poll["status"] == "succeeded":
                return jsonify({"image_url": poll["output"][0]})
            elif poll["status"] == "failed":
                return jsonify({"error": "Image generation failed"}), 500
            time.sleep(1)

    except Exception as e:
        return jsonify({"error": f"Style Photo error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
