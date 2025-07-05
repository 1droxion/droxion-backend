from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
from collections import Counter
from dateutil import parser
import pytz
import stripe
import subprocess

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://droxion-live-final.vercel.app"], supports_credentials=True)

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

def load_paid_users():
    if os.path.exists(PAID_USER_FILE):
        with open(PAID_USER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_paid_users(data):
    with open(PAID_USER_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/")
def home():
    return "✅ Droxion Flask Backend is live."

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return f"❌ Webhook error: {str(e)}", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id", "")
        print("✅ Stripe payment complete for:", user_id)
        users = load_paid_users()
        users[user_id] = {"paid": True, "date": datetime.utcnow().isoformat()}
        save_paid_users(users)

    return jsonify(success=True)

@app.route("/check-paid", methods=["POST"])
def check_paid():
    data = request.json
    user_id = data.get("user_id", "")
    if not user_id:
        return jsonify({"paid": False}), 400
    users = load_paid_users()
    is_paid = users.get(user_id, {}).get("paid", False)
    return jsonify({"paid": is_paid})

@app.route("/track", methods=["POST"])
def track():
    data = request.json
    log_user_action(
        data.get("user_id", "anonymous"),
        data.get("action", ""),
        data.get("input", ""),
        get_client_ip()
    )
    return jsonify({"ok": True})

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400
        log_user_action(data.get("user_id", "anonymous"), "message", prompt, get_client_ip())
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

@app.route("/generate-veo", methods=["POST"])
def generate_veo():
    try:
        data = request.json
        topic = data.get("topic", "Success")
        print("🎬 Generating video for:", topic)

        result = subprocess.run(
            ["python", "your_video_script.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if result.returncode == 0:
            last_line = result.stdout.decode().strip().split("\n")[-1]
            filename = last_line if last_line.endswith(".mp4") else None
            if filename:
                return jsonify({"videoUrl": f"/static/generated/{filename}"})
        print(result.stderr.decode())
        return jsonify({"error": "Failed to generate video."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
