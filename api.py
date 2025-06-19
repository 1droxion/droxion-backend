from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
import uuid
from datetime import datetime, timedelta
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
        user_id = data.get("userId", f"user-{uuid.uuid4().hex[:8]}")
        ip = request.remote_addr
        location = os.getenv("USER_LOCATION", "")

        log_event(user_id, "message", prompt, ip, location)

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

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "")
    if token != "droxion2025":
        return "❌ Unauthorized", 401

    try:
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)
    except:
        logs = []

    now = datetime.now(pytz.utc)
    daily_users, weekly_users, monthly_users = set(), set(), set()
    hours, top_inputs, top_users, top_locations = {}, {}, {}, {}

    for log in logs:
        try:
            timestamp = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
        except:
            continue

        user = log.get("user_id", "anonymous")
        ip = log.get("ip", "")
        location = log.get("location", "")
        text = log.get("input", "").strip()

        delta = now - timestamp
        if delta <= timedelta(days=1): daily_users.add(user)
        if delta <= timedelta(days=7): weekly_users.add(user)
        if delta <= timedelta(days=30): monthly_users.add(user)

        hours[timestamp.hour] = hours.get(timestamp.hour, 0) + 1
        if text: top_inputs[text] = top_inputs.get(text, 0) + 1
        top_users[user] = top_users.get(user, 0) + 1
        if location: top_locations[location] = top_locations.get(location, 0) + 1

    table = "<table border=1 cellpadding=8><tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>"
    for log in reversed(logs[-20:]):
        table += f"<tr><td>{log['timestamp']}</td><td>{log.get('user_id','')}</td><td>{log['action']}</td><td>{log.get('input','')}</td><td>{log.get('ip','')}</td><td>{log.get('location','')}</td></tr>"
    table += "</table>"

    return render_template_string(f"""
    <html style='background:#111;color:white;padding:2rem;font-family:sans-serif'>
      <h2>📊 Droxion Dashboard</h2>
      <p><b>DAU:</b> {len(daily_users)} | <b>WAU:</b> {len(weekly_users)} | <b>MAU:</b> {len(monthly_users)}</p>
      <p><b>Peak usage hour:</b> {max(hours, key=hours.get) if hours else 0}:00</p>
      <p><b>Top Users:</b> {top_users}</p>
      <p><b>Top Locations:</b> {top_locations}</p>
      <p><b>Top Inputs:</b> {top_inputs}</p>
      <p><i>Filter: ?token=droxion2025&days=7&user=yourid</i></p>
      <h3>User Activity Logs</h3>
      {table}
    </html>
    """)

def log_event(user_id, action, input_text, ip, location):
    log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "action": action,
        "input": input_text,
        "ip": ip,
        "location": location
    }
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        else:
            logs = []
    except:
        logs = []
    logs.append(log)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
