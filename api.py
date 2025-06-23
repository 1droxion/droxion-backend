from flask import Flask, request, jsonify, make_response, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json
from datetime import datetime, timedelta
from collections import defaultdict
from dateutil import parser
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")
LOG_FILE = "user_logs.json"
TIMEZONE = pytz.timezone("US/Central")

with open("world_knowledge.json") as f:
    WORLD_DATA = json.load(f)

MEMORY_FILE = "user_memory.json"
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE) as f:
        USER_MEMORY = json.load(f)
else:
    USER_MEMORY = {}

def save_user_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(USER_MEMORY, f, indent=2)

def log_user_action(user_id, ip, action_type):
    now = datetime.now(TIMEZONE).isoformat()
    entry = {
        "user_id": user_id,
        "ip": ip,
        "action": action_type,
        "timestamp": now
    }
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            logs = json.load(f)
    logs.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def calculate_user_stats():
    if not os.path.exists(LOG_FILE):
        return [], 0, 0, 0
    with open(LOG_FILE) as f:
        logs = json.load(f)
    today = datetime.now(TIMEZONE).date()
    one_week = today - timedelta(days=7)
    one_month = today - timedelta(days=30)
    dau, wau, mau = set(), set(), set()
    for log in logs:
        day = parser.parse(log["timestamp"]).date()
        uid = log["user_id"]
        if day == today: dau.add(uid)
        if day >= one_week: wau.add(uid)
        if day >= one_month: mau.add(uid)
    return logs, len(dau), len(wau), len(mau)

@app.after_request
def cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    return make_response("", 204)

@app.route("/dashboard")
def dashboard():
    if request.args.get("token") != ADMIN_TOKEN:
        return "Unauthorized", 403
    logs, dau, wau, mau = calculate_user_stats()
    rows = "".join([f"<tr><td>{x['user_id']}</td><td>{x['ip']}</td><td>{x['action']}</td><td>{x['timestamp']}</td></tr>" for x in reversed(logs[-200:])])
    return render_template_string(f"""
    <html><head><style>
    body {{ background:#000; color:#0f0; font-family:monospace; }}
    table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
    td,th {{ border:1px solid #0f0; padding:5px; }}
    </style></head><body>
    <h2>Droxion Dashboard</h2>
    <p>DAU: {dau} | WAU: {wau} | MAU: {mau}</p>
    <table><tr><th>User ID</th><th>IP</th><th>Action</th><th>Time</th></tr>{rows}</table>
    </body></html>
    """)

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        user_id = data.get("user_id", "anon")
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        voice_mode = data.get("voiceMode", False)

        q = prompt.lower()
        if "my name is" in q:
            name = prompt.split("my name is")[-1].split()[0]
            USER_MEMORY[user_id] = {"name": name}
            save_user_memory()
            return jsonify({"reply": f"Nice to meet you, {name}!"})
        if "what's my name" in q:
            name = USER_MEMORY.get(user_id, {}).get("name", "not saved yet")
            return jsonify({"reply": f"You said your name is {name}."})
        if "who made you" in q or "your creator" in q:
            return jsonify({"reply": "I was created by Dhruv Patel, the founder of Droxion."})

        if "video" in q or "youtube" in q or "watch" in q:
            log_user_action(user_id, ip, "video")
            return jsonify({"reply": "📺 Here's a video you might enjoy:", "videoUrl": "https://www.youtube.com/watch?v=I6LWYEc4M4U"})

        if "image" in q or "photo" in q or "picture" in q:
            log_user_action(user_id, ip, "image")
            return jsonify({"reply": f"🖼️ Generating image for \"{prompt}\"...", "imagePrompt": prompt})

        log_user_action(user_id, ip, "chat")
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are Droxion AI built by Dhruv Patel."},
                {"role": "user", "content": prompt}
            ]
        }
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply, "voiceMode": voice_mode})

    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
