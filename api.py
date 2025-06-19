from flask import Flask, request, jsonify, make_response
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser
from collections import Counter

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": [
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
]}})

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
            {"role": "system", "content": "You are an AI assistant created by Dhruv Patel and powered by Droxion™."},
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

@app.route("/track", methods=["POST"])
@cross_origin()
def track():
    try:
        data = request.json
        user_id = data.get("user_id")
        action = data.get("action")
        input_text = data.get("input")
        timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        ip = request.remote_addr
        location = request.headers.get("X-Location", "")

        if not user_id or not action:
            return jsonify({"error": "Missing user_id or action."}), 400

        log = {
            "user_id": user_id,
            "action": action,
            "input": input_text,
            "timestamp": timestamp,
            "ip": ip,
            "location": location
        }

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

@app.route("/dashboard")
@cross_origin()
def dashboard():
    token = request.args.get("token")
    if token != "droxion2025":
        return "❌ Unauthorized", 403

    if not os.path.exists(LOG_FILE):
        return "<h3>No activity logs found.</h3>"

    with open(LOG_FILE) as f:
        logs = json.load(f)

    now = datetime.now(timezone.utc)
    days = int(request.args.get("days", 30))
    filter_user = request.args.get("user")

    filtered_logs = []
    users_1d, users_7d, users_30d = set(), set(), set()
    hour_usage = []
    user_counts = Counter()
    locations = Counter()
    queries = Counter()

    for log in logs:
        t = parser.isoparse(log["timestamp"])
        uid = log["user_id"]
        if now - t <= timedelta(days=1): users_1d.add(uid)
        if now - t <= timedelta(days=7): users_7d.add(uid)
        if now - t <= timedelta(days=30): users_30d.add(uid)

        if now - t <= timedelta(days=days):
            if not filter_user or uid == filter_user:
                filtered_logs.append(log)
                hour_usage.append(t.hour)
                user_counts[uid] += 1
                if log.get("location"): locations[log["location"]] += 1
                if log.get("input"): queries[log["input"]] += 1

    peak_hour = Counter(hour_usage).most_common(1)
    top_locations = locations.most_common(3)
    top_queries = queries.most_common(5)

    html = f"""
    <html><head><title>Droxion Dashboard</title>
    <style>
    body {{ background: #111; color: #eee; font-family: sans-serif; padding: 20px; }}
    .card {{ background: #222; padding: 10px; margin: 8px 0; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th, td {{ border: 1px solid #444; padding: 6px; font-size: 13px; }}
    th {{ background-color: #222; }}
    tr:nth-child(even) {{ background-color: #1a1a1a; }}
    </style></head><body>
    <h2>📊 Droxion Dashboard</h2>
    <div class='card'>DAU: {len(users_1d)} | WAU: {len(users_7d)} | MAU: {len(users_30d)}</div>
    <div class='card'>Peak usage hour: {peak_hour[0][0]}:00</div>
    <div class='card'>Top Users: {dict(user_counts.most_common(3))}</div>
    <div class='card'>Top Locations: {dict(top_locations)}</div>
    <div class='card'>Top Inputs: {dict(top_queries)}</div>
    <div class='card'>Filter: ?token=droxion2025&days=7&user=yourid</div>
    <h3>User Activity Logs</h3>
    <table>
    <tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
    """
    for log in reversed(filtered_logs[-100:]):
        html += f"<tr><td>{log['timestamp']}</td><td>{log['user_id']}</td><td>{log['action']}</td><td>{log.get('input','')}</td><td>{log.get('ip','')}</td><td>{log.get('location','')}</td></tr>"

    html += "</table></body></html>"
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
