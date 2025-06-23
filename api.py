from flask import Flask, request, jsonify, render_template_string, make_response
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime, timedelta
from collections import Counter
from dateutil import parser
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

LOG_FILE = "user_logs.json"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

# === Load World Knowledge ===
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

def update_memory(user_id, prompt):
    q = prompt.lower()
    if "my name is" in q:
        name = prompt.split("my name is")[-1].strip().split()[0]
        USER_MEMORY.setdefault(user_id, {})["name"] = name
        save_user_memory()
        return f"Nice to meet you, {name}!"
    if "i live in" in q or "i am from" in q:
        for phrase in ["i live in", "i am from"]:
            if phrase in q:
                loc = prompt.split(phrase)[-1].strip().split()[0]
                USER_MEMORY.setdefault(user_id, {})["location"] = loc
                save_user_memory()
                return f"Got it, you live in {loc}."
    return None

def recall_memory(user_id, prompt):
    q = prompt.lower()
    user_data = USER_MEMORY.get(user_id, {})
    if "what's my name" in q or "what is my name" in q:
        return f"You said your name is {user_data.get('name', 'not saved yet')}."
    if "where do i live" in q:
        return f"You said you live in {user_data.get('location', 'an unknown place')}."
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
    for planet, d in WORLD_DATA.get("planets", {}).items():
        if planet.lower() in q:
            return f"{planet} is the {d['position']} planet from the sun and is a {d['type']}."
    for code, name in WORLD_DATA.get("currencies", {}).items():
        if code.lower() in q or name.lower() in q:
            return f"{code} stands for {name}."
    for lang, regions in WORLD_DATA.get("languages", {}).items():
        if lang.lower() in q:
            return f"{lang} is spoken in {', '.join(regions)}."
    if "ai company" in q or "top ai" in q:
        return f"Top AI companies are: {', '.join(WORLD_DATA['tech']['top_ai_companies'])}."
    if "gpt" in q:
        return f"Available GPT models are: {', '.join(WORLD_DATA['tech']['gpt_models'])}."
    return None

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user_id = data.get("user_id", "anonymous")
        voice_mode = data.get("voiceMode", False)
        video_mode = data.get("videoMode", False)

        # === Log user activity ===
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "prompt": prompt,
            "ip": ip
        }
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        # Memory Save
        reply = update_memory(user_id, prompt)
        if reply:
            return jsonify({"reply": reply, "voiceMode": voice_mode, "videoMode": video_mode})

        # Memory Recall
        reply = recall_memory(user_id, prompt)
        if reply:
            return jsonify({"reply": reply, "voiceMode": voice_mode, "videoMode": video_mode})

        # World Facts
        reply = get_world_answer(prompt)
        if reply:
            return jsonify({"reply": reply, "voiceMode": voice_mode, "videoMode": video_mode})

        # GPT fallback
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

@app.route("/dashboard", methods=["GET"])
def dashboard():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        return "❌ Unauthorized", 401

    try:
        with open(LOG_FILE) as f:
            logs = []
            for line in f:
                try:
                    log = json.loads(line)
                    if isinstance(log, dict):
                        logs.append(log)
                except:
                    continue

        now = datetime.utcnow()
        today = now.date()
        past_week = today - timedelta(days=7)
        past_month = today - timedelta(days=30)

        def count_users(since):
            return len(set(
                log["user_id"]
                for log in logs
                if "timestamp" in log and parser.isoparse(log["timestamp"]).date() >= since
            ))

        dau = count_users(today)
        wau = count_users(past_week)
        mau = count_users(past_month)

        html = f"""
        <html><body style='font-family:sans-serif;background:#000;color:#0f0;padding:20px'>
        <h1>📊 Droxion Dashboard</h1>
        <p><b>DAU:</b> {dau}</p>
        <p><b>WAU:</b> {wau}</p>
        <p><b>MAU:</b> {mau}</p>
        <hr>
        <h3>Recent Logs</h3>
        <pre style='background:#111;color:#0f0;padding:10px;border-radius:10px;max-height:400px;overflow:auto'>{json.dumps(logs[-10:], indent=2)}</pre>
        </body></html>
        """
        return render_template_string(html)

    except Exception as e:
        return f"❌ Error loading dashboard: {str(e)}", 500

# ✅ Port binding for Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
