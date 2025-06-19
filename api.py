from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import json
import base64
import time
from datetime import datetime
from collections import Counter
from dateutil import parser
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
])

LOG_FILE = "user_logs.json"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

# --- UTILS ---

def get_location_from_ip(ip):
    try:
        # Take first IP if multiple
        main_ip = ip.split(",")[0].strip()
        res = requests.get(f"http://ip-api.com/json/{main_ip}")
        data = res.json()
        if data["status"] == "success":
            return f"{data['city']}, {data['countryCode']}"
        return ""
    except:
        return ""

def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)

def log_user_action(user_id, action, input_text, ip):
    now = datetime.utcnow().isoformat() + "Z"
    location = get_location_from_ip(ip)
    new_entry = {
        "timestamp": now,
        "user_id": user_id,
        "action": action,
        "input": input_text,
        "ip": ip,
        "location": location
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        except:
            logs = []

    logs.append(new_entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def parse_logs(file_path, user_filter=None, days=7):
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    dau_set, wau_set, mau_set = set(), set(), set()
    hour_count = Counter()
    input_count = Counter()
    user_count = Counter()
    location_count = Counter()
    logs = []

    if os.path.exists(file_path):
        with open(file_path) as f:
            data = json.load(f)
        for entry in data:
            try:
                ts = parser.isoparse(entry["timestamp"]).replace(tzinfo=pytz.UTC)
                if (now - ts).days <= days:
                    uid = entry.get("user_id", "anonymous")
                    logs.append(entry)
                    dau_set.add(uid)
                    wau_set.add(uid)
                    mau_set.add(uid)
                    hour = ts.hour
                    hour_count[hour] += 1
                    input_count[entry.get("input", "").strip()] += 1
                    user_count[uid] += 1
                    location_count[entry.get("location", "")] += 1
            except:
                continue
    return {
        "dau": len(dau_set),
        "wau": len(wau_set),
        "mau": len(mau_set),
        "peak_hour": hour_count.most_common(1)[0][0] if hour_count else 0,
        "top_users": dict(user_count.most_common(3)),
        "top_inputs": dict(input_count.most_common(5)),
        "top_locations": dict(location_count.most_common(3)),
        "logs": logs[-100:]
    }

# --- ROUTES ---

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        ip = get_client_ip()
        user_id = data.get("user_id", "anonymous")
        voice_mode = data.get("voiceMode", False)
        video_mode = data.get("videoMode", False)

        log_user_action(user_id, "message", prompt, ip)

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
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
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({
            "reply": reply,
            "voiceMode": voice_mode,
            "videoMode": video_mode
        })
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        headers = {
            "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            "input": {
                "prompt": prompt,
                "width": 768,
                "height": 768
            }
        }

        r = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload).json()
        poll_url = r["urls"]["get"]

        while True:
            poll = requests.get(poll_url, headers=headers).json()
            if poll["status"] == "succeeded":
                return jsonify({"image_url": poll["output"]})
            elif poll["status"] == "failed":
                return jsonify({"error": "Image generation failed"}), 500
            time.sleep(1)
    except Exception as e:
        return jsonify({"error": f"Image error: {str(e)}"}), 500

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

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        return "❌ Unauthorized", 401
    user_filter = request.args.get("user")
    days = int(request.args.get("days", 7))
    stats = parse_logs(LOG_FILE, user_filter, days)

    html = """
    <h2>📊 Droxion Dashboard</h2>
    <div>DAU: {{stats['dau']}} | WAU: {{stats['wau']}} | MAU: {{stats['mau']}}</div>
    <div>Peak Hour: {{stats['peak_hour']}}</div>
    <div>Top Users: {{stats['top_users']}}</div>
    <div>Top Inputs: {{stats['top_inputs']}}</div>
    <div>Top Locations: {{stats['top_locations']}}</div>
    <hr>
    <h4>User Activity Logs</h4>
    <table border="1" cellpadding="5">
        <tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
        {% for log in stats['logs'] %}
        <tr>
            <td>{{log["timestamp"]}}</td>
            <td>{{log["user_id"]}}</td>
            <td>{{log["action"]}}</td>
            <td>{{log["input"]}}</td>
            <td>{{log["ip"]}}</td>
            <td>{{log["location"]}}</td>
        </tr>
        {% endfor %}
    </table>
    """
    return render_template_string(html, stats=stats)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
