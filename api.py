from flask import Flask, request, jsonify, Response, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
from collections import Counter
from datetime import datetime, timedelta
from dateutil import parser
from pytz import utc

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
])

LOG_FILE = "user_logs.json"
ALLOWED_TOKENS = ["droxion2025"]

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
        user_id = data.get("userId", "anonymous")
        user_ip = request.remote_addr

        log_action(user_id, "message", prompt, user_ip)

        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

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

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "")
    if token not in ALLOWED_TOKENS:
        return Response("❌ Unauthorized", status=401)

    try:
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)
    except:
        logs = []

    now = datetime.utcnow().replace(tzinfo=utc)
    dau_cutoff = now - timedelta(days=1)
    wau_cutoff = now - timedelta(weeks=1)
    mau_cutoff = now - timedelta(days=30)

    daus = set()
    waus = set()
    maus = set()
    hour_counter = Counter()
    input_counter = Counter()
    user_counter = Counter()
    location_counter = Counter()

    rows = []
    for entry in logs:
        try:
            t = parser.isoparse(entry["timestamp"])
            uid = entry.get("user_id", "anon")
            ip = entry.get("ip", "?")
            loc = entry.get("location", "")

            if t > dau_cutoff:
                daus.add(uid)
            if t > wau_cutoff:
                waus.add(uid)
            if t > mau_cutoff:
                maus.add(uid)

            hour_counter[t.strftime("%H:00")] += 1
            input_counter[entry.get("input", "")] += 1
            user_counter[uid] += 1
            location_counter[loc] += 1

            rows.append(entry)
        except:
            continue

    html = f"""
    <html><body style='background:#111;color:white;padding:2rem;'>
    <h2>📊 Droxion Dashboard</h2>
    <p>DAU: {len(daus)} | WAU: {len(waus)} | MAU: {len(maus)}</p>
    <p>Peak usage hour: {hour_counter.most_common(1)[0][0] if hour_counter else 'N/A'}</p>
    <p>Top Users: {dict(user_counter.most_common(3))}</p>
    <p>Top Locations: {dict(location_counter.most_common(3))}</p>
    <p>Top Inputs: {dict(input_counter.most_common(4))}</p>
    <hr/>
    <p><code>Filter: ?token=droxion2025&days=7&user=yourid</code></p>
    <h3>User Activity Logs</h3>
    <table border='1' cellspacing='0' cellpadding='6'>
        <tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
    """

    for r in rows[-100:][::-1]:
        html += f"<tr><td>{r['timestamp']}</td><td>{r['user_id']}</td><td>{r['action']}</td><td>{r['input']}</td><td>{r.get('ip','')}</td><td>{r.get('location','')}</td></tr>"

    html += "</table></body></html>"
    return render_template_string(html)

def log_action(user_id, action, text, ip):
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "action": action,
        "input": text,
        "ip": ip
    }

    try:
        geo = requests.get(f"https://ipinfo.io/{ip}/json").json()
        city = geo.get("city", "")
        region = geo.get("region", "")
        country = geo.get("country", "")
        entry["location"] = ", ".join([city, region, country]).strip(', ')
    except:
        entry["location"] = ""

    try:
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
    except:
        data = []

    data.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
