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
CORS(app, origins="*", supports_credentials=True)

LOG_FILE = "user_logs.json"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

# === Load World Knowledge ===
with open("world_knowledge.json") as f:
    WORLD_DATA = json.load(f)

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

def get_location_from_ip(ip):
    try:
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

        world_reply = get_world_answer(prompt)
        if world_reply:
            return jsonify({
                "reply": world_reply,
                "voiceMode": voice_mode,
                "videoMode": video_mode
            })

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
