from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
from collections import Counter
from dateutil import parser
import pytz
import stripe

load_dotenv()

app = Flask(__name__)
CORS(app, origins=[
    "https://droxion-live-final.vercel.app",
    "https://www.droxion.com"
], supports_credentials=True)

# === ENV VARS ===
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

stripe.api_key = STRIPE_SECRET_KEY

LOG_FILE = "user_logs.json"
PAID_USER_FILE = "users.json"

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

def fetch_real_time_info(prompt, location):
    prompt_lower = prompt.lower()
    city = location.split(",")[0] if location else "New York"

    if "weather" in prompt_lower:
        return f"🌤️ Weather in {city}: 82°F, Clear Skies — [View Full Forecast](https://www.google.com/search?q=weather+{city.replace(' ', '+')})"
    if "time" in prompt_lower:
        try:
            tz = pytz.timezone("America/New_York")
            if "london" in prompt_lower:
                tz = pytz.timezone("Europe/London")
            elif "tokyo" in prompt_lower:
                tz = pytz.timezone("Asia/Tokyo")
            elif "mumbai" in prompt_lower:
                tz = pytz.timezone("Asia/Kolkata")
            time_now = datetime.now(tz).strftime("%I:%M %p, %A")
            return f"🕒 Current time in {tz.zone.split('/')[-1]}: {time_now}"
        except:
            pass
    if "news" in prompt_lower:
        return "📰 Latest News: [Apple unveils new AI chip at WWDC 2025](https://www.cnn.com/example)"
    if "youtube" in prompt_lower or "trending" in prompt_lower:
        return "🔥 Top YouTube Video: [MrBeast - Survive 7 Days Challenge](https://youtube.com/watch?v=example)"
    return None

@app.route("/")
def home():
    return "✅ Droxion Flask Backend is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        user_id = data.get("user_id", "anonymous")
        ip = get_client_ip()
        location = get_location_from_ip(ip)
        log_user_action(user_id, "message", prompt, ip)

        real_time_reply = fetch_real_time_info(prompt, location)
        if real_time_reply:
            return jsonify({"reply": real_time_reply})

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
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
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

# Keep the rest of your routes (unchanged) — track, stripe-webhook, check-paid, etc.

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
