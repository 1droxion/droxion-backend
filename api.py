from flask import Flask, request, jsonify
from flask_cors import CORS
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

@app.route("/track", methods=["POST"])
def track():
    try:
        data = request.json
        user_id = data.get("user_id")
        action = data.get("action")
        input_text = data.get("input")
        timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        ip = request.remote_addr
        location = request.headers.get("X-Location", "")  # optional, can send from frontend

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
def dashboard():
    token = request.args.get("token")
    if token != "droxion2025":
        return "❌ Unauthorized", 403

    if not os.path.exists(LOG_FILE):
        return "<h3>No activity logs found.</h3>"

    with open(LOG_FILE) as f:
        logs = json.load(f)

    now = datetime.now(timezone.utc)
    users_1d, users_7d, users_30d = set(), set(), set()

    for log in logs:
        t = parser.isoparse(log["timestamp"])
        uid = log["user_id"]
        if now - t <= timedelta(days=1):
            users_1d.add(uid)
        if now - t <= timedelta(days=7):
            users_7d.add(uid)
        if now - t <= timedelta(days=30):
            users_30d.add(uid)

    return f"""
    <html><head><title>Droxion Dashboard</title>
    <script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
    <style>
    body {{ background: #111; color: #eee; font-family: sans-serif; padding: 20px; }}
    canvas {{ background: #222; border-radius: 12px; }}
    </style>
    </head><body>
    <h2>📊 Droxion Usage Dashboard</h2>
    <canvas id='chart' width='400' height='200'></canvas>
    <script>
    const ctx = document.getElementById('chart').getContext('2d');
    new Chart(ctx, {{
        type: 'bar',
        data: {{
            labels: ['DAU', 'WAU', 'MAU'],
            datasets: [{{
                label: 'Active Users',
                data: [{len(users_1d)}, {len(users_7d)}, {len(users_30d)}],
                backgroundColor: ['#fff', '#ccc', '#888'],
            }}]
        }},
        options: {{
            plugins: {{ legend: {{ labels: {{ color: 'white' }} }} }},
            scales: {{
                y: {{ ticks: {{ color: 'white' }} }},
                x: {{ ticks: {{ color: 'white' }} }}
            }}
        }}
    }});
    </script></body></html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
