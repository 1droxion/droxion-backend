from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
from datetime import datetime, timedelta
from collections import Counter
from dateutil import parser

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[
    "https://www.droxion.com",
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
        user_id = data.get("user_id", "anonymous")

        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        # Log the message
        log_user_action(user_id, "message", prompt)

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
            {"role": "system", "content": "You are an assistant created by Dhruv Patel, named Droxion."},
            {"role": "user", "content": prompt}
        ]
        payload = {"model": "gpt-4", "messages": messages}
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]

        return jsonify({"reply": reply, "videoMode": video_mode, "voiceMode": voice_mode})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

@app.route("/track", methods=["POST"])
def track():
    try:
        data = request.json
        user_id = data.get("user_id", "anonymous")
        action = data.get("action", "unknown")
        input_text = data.get("input", "")
        ip = request.remote_addr or "unknown"
        location = ""

        try:
            loc_res = requests.get(f"https://ipapi.co/{ip}/country_name/")
            if loc_res.status_code == 200:
                location = loc_res.text.strip()
        except:
            location = ""

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "action": action,
            "input": input_text,
            "ip": ip,
            "location": location
        }

        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        else:
            logs = []

        logs.append(log_entry)
        with open(LOG_FILE, "w") as f:
            json.dump(logs, f)

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard")
def dashboard():
    try:
        token = request.args.get("token")
        if token != os.getenv("ADMIN_TOKEN"):
            return "<h1>❌ Unauthorized</h1>", 403

        user_filter = request.args.get("user")
        days = int(request.args.get("days", 7))
        cutoff = datetime.utcnow() - timedelta(days=days)

        if not os.path.exists(LOG_FILE):
            return "No data"

        with open(LOG_FILE, "r") as f:
            logs = json.load(f)

        logs = [log for log in logs if parser.parse(log["timestamp"]) >= cutoff]
        if user_filter:
            logs = [log for log in logs if log["user_id"] == user_filter]

        dau = len(set(log["user_id"] for log in logs if (datetime.utcnow() - parser.parse(log["timestamp"])) < timedelta(days=1)))
        wau = len(set(log["user_id"] for log in logs if (datetime.utcnow() - parser.parse(log["timestamp"])) < timedelta(days=7)))
        mau = len(set(log["user_id"] for log in logs if (datetime.utcnow() - parser.parse(log["timestamp"])) < timedelta(days=30)))

        hours = [parser.parse(log["timestamp"]).hour for log in logs]
        peak_hour = Counter(hours).most_common(1)[0][0] if hours else "N/A"

        users = Counter(log["user_id"] for log in logs)
        locations = Counter(log["location"] for log in logs)
        inputs = Counter(log["input"] for log in logs)

        html = f"""
        <html><head><title>Droxion Dashboard</title></head><body style='background:black;color:white;font-family:sans-serif'>
        <h2>📊 Droxion Dashboard</h2>
        <p>DAU: {dau} | WAU: {wau} | MAU: {mau}</p>
        <p>Peak usage hour: {peak_hour}:00</p>
        <p>Top Users: {dict(users)}</p>
        <p>Top Locations: {dict(locations)}</p>
        <p>Top Inputs: {dict(inputs)}</p>
        <p><small>Filter: ?token=yourtoken&days=7&user=yourid</small></p>
        <h3>User Activity Logs</h3>
        <table border='1' cellpadding='4' cellspacing='0' style='color:white'>
            <tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
        """
        for log in logs[-100:][::-1]:
            html += f"<tr><td>{log['timestamp']}</td><td>{log['user_id']}</td><td>{log['action']}</td><td>{log['input']}</td><td>{log['ip']}</td><td>{log.get('location','')}</td></tr>"

        html += "</table></body></html>"
        return html
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
