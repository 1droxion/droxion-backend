from flask import Flask, request, jsonify, make_response, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json
from datetime import datetime, timedelta
from collections import defaultdict
from dateutil import parser  # ✅ Required for date parsing
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")
LOG_FILE = "user_logs.json"
TIMEZONE = pytz.timezone("US/Central")

# === Load world knowledge ===
with open("world_knowledge.json") as f:
    WORLD_DATA = json.load(f)

# === Load or Init Memory ===
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
    one_week_ago = today - timedelta(days=7)
    one_month_ago = today - timedelta(days=30)

    active_today, active_week, active_month = set(), set(), set()

    for log in logs:
        log_time = parser.parse(log["timestamp"]).date()
        uid = log["user_id"]
        if log_time == today:
            active_today.add(uid)
        if log_time >= one_week_ago:
            active_week.add(uid)
        if log_time >= one_month_ago:
            active_month.add(uid)

    return logs, len(active_today), len(active_week), len(active_month)

def update_memory(user_id, prompt):
    q = prompt.lower()
    if "my name is" in q:
        name = prompt.split("my name is")[-1].strip().split()[0]
        USER_MEMORY.setdefault(user_id, {})["name"] = name
        save_user_memory()
        return f"Nice to meet you, {name}!"
    if "i live in" in q or "i am from" in q:
        for tag in ["i live in", "i am from"]:
            if tag in q:
                loc = prompt.split(tag)[-1].strip().split()[0]
                USER_MEMORY.setdefault(user_id, {})["location"] = loc
                save_user_memory()
                return f"Got it, you live in {loc}."
    return None

def recall_memory(user_id, prompt):
    q = prompt.lower()
    user = USER_MEMORY.get(user_id, {})
    if "what's my name" in q or "what is my name" in q:
        return f"You said your name is {user.get('name', 'not saved yet')}."
    if "where do i live" in q:
        return f"You said you live in {user.get('location', 'unknown place')}."
    return None

def get_world_answer(prompt):
    q = prompt.lower()
    for c, d in WORLD_DATA.get("countries", {}).items():
        if c.lower() in q:
            if "capital" in q:
                return f"The capital of {c} is {d['capital']}."
            elif "currency" in q:
                return f"The currency of {c} is {d['currency']}."
            elif "population" in q:
                return f"The population of {c} is {d['population']}."
    for p, d in WORLD_DATA.get("planets", {}).items():
        if p.lower() in q:
            return f"{p} is the {d['position']} planet and is a {d['type']}."
    for code, name in WORLD_DATA.get("currencies", {}).items():
        if code.lower() in q or name.lower() in q:
            return f"{code} stands for {name}."
    for lang, regions in WORLD_DATA.get("languages", {}).items():
        if lang.lower() in q:
            return f"{lang} is spoken in {', '.join(regions)}."
    if "top ai" in q:
        return f"Top AI companies: {', '.join(WORLD_DATA['tech']['top_ai_companies'])}."
    if "gpt" in q:
        return f"Available GPT models: {', '.join(WORLD_DATA['tech']['gpt_models'])}."
    return None

def custom_reply(prompt):
    q = prompt.lower()
    if any(tag in q for tag in ["who made you", "who created you", "your creator", "your owner", "founder", "droxion", "dhruv patel"]):
        return "I was created by Dhruv Patel, the founder of Droxion. I'm your personal AI Assistant."
    return None

def get_youtube_response(prompt):
    q = prompt.lower()
    if any(x in q for x in ["video", "youtube", "watch", "episode", "movie"]):
        return {
            "reply": "🎬 Here's a video you might enjoy:",
            "videoUrl": "https://www.youtube.com/watch?v=I6LWYEc4M4U",
            "videoMode": True
        }
    return None

def detect_image_prompt(prompt):
    if any(x in prompt.lower() for x in ["image", "photo", "picture", "drawing"]):
        return {
            "reply": "🖼️ Generating image...",
            "imagePrompt": prompt,
            "imageMode": True
        }
    return None

@app.after_request
def cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    return make_response("", 204)

@app.route("/dashboard", methods=["GET"])
def dashboard():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return "Unauthorized", 403

    logs, dau, wau, mau = calculate_user_stats()
    rows = ""
    for log in reversed(logs[-200:]):  # show last 200 logs
        rows += f"<tr><td>{log['user_id']}</td><td>{log['ip']}</td><td>{log['action']}</td><td>{log['timestamp']}</td></tr>"

    return render_template_string(f"""
    <html>
    <head>
        <title>Droxion Dashboard</title>
        <style>
            body {{ background:#111; color:#0f0; font-family:monospace; padding:20px; }}
            table {{ width:100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #0f0; padding: 5px; text-align: left; }}
        </style>
    </head>
    <body>
        <h2>Droxion Dashboard</h2>
        <p>DAU: {dau} | WAU: {wau} | MAU: {mau}</p>
        <table>
            <tr><th>User ID</th><th>IP Address</th><th>Action</th><th>Time</th></tr>
            {rows}
        </table>
    </body>
    </html>
    """)

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        user_id = data.get("user_id", "anonymous")
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        voice_mode = data.get("voiceMode", False)

        # === Fast logic
        for fn in [update_memory, recall_memory, get_world_answer, custom_reply]:
            r = fn(user_id, prompt) if fn in [update_memory, recall_memory] else fn(prompt)
            if r:
                log_user_action(user_id, ip, "chat")
                return jsonify({"reply": r, "voiceMode": voice_mode})

        video = get_youtube_response(prompt)
        if video:
            log_user_action(user_id, ip, "video")
            return jsonify({**video})

        image = detect_image_prompt(prompt)
        if image:
            log_user_action(user_id, ip, "image")
            return jsonify({**image})

        # === Fallback to GPT
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
        log_user_action(user_id, ip, "chat")
        return jsonify({"reply": reply, "voiceMode": voice_mode})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
