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
    "https://www.droxion.com",
    "https://droxion.com"
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

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            "input": { "prompt": prompt, "width": 768, "height": 768 }
        }
        r = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload).json()
        poll_url = r["urls"]["get"]
        while True:
            poll = requests.get(poll_url, headers=headers).json()
            if poll["status"] == "succeeded":
                return jsonify({"image_url": poll["output"]})
            elif poll["status"] == "failed":
                return jsonify({"error": "Image generation failed"}), 500
            time.sleep(1)
    except Exception as e:
        return jsonify({"error": f"Image error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "")
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": prompt,
            "type": "video",
            "maxResults": 1,
            "key": YOUTUBE_API_KEY
        }
        res = requests.get(url, params=params).json()
        item = res["items"][0]
        return jsonify({
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        })
    except Exception as e:
        return jsonify({"error": f"YouTube error: {str(e)}"}), 500

@app.route("/generate", methods=["POST"])
def generate_video():
    try:
        data = request.json
        topic = data.get("topic", "Success")
        return jsonify({
            "videoUrl": "/static/fake_videos/sample.mp4"
        })
    except Exception as e:
        return jsonify({"error": f"Video generation error: {str(e)}"}), 500

@app.route("/user-stats")
def user_stats():
    try:
        user_id = request.args.get("user_id", "anonymous")
        logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)

        video_count = sum(1 for l in logs if l.get("action") == "generate" and l.get("user_id") == user_id)
        users = load_paid_users()
        user_plan = "Starter"
        video_limit = 5
        credits = 0

        if users.get(user_id, {}).get("paid"):
            user_plan = "Pro"
            video_limit = 100
            credits = 50

        return jsonify({
            "user": user_id,
            "plan": {
                "name": user_plan,
                "videoLimit": video_limit
            },
            "videosThisMonth": video_count,
            "credits": credits
        })
    except Exception as e:
        return jsonify({"error": f"user-stats error: {str(e)}"}), 500

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        return "❌ Unauthorized", 401
    days = int(request.args.get("days", 7))
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    dau_set, wau_set, mau_set = set(), set(), set()
    hour_count = Counter()
    input_count = Counter()
    user_count = Counter()
    location_count = Counter()
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
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
                    hour_count[ts.hour] += 1
                    input_count[entry.get("input", "").strip()] += 1
                    user_count[uid] += 1
                    location_count[entry.get("location", "")] += 1
            except:
                continue
    html = """
    <style>body{background:#000;color:#fff;font-family:Arial;padding:20px;}table{border-collapse:collapse;width:100%;margin-top:20px;}th,td{border:1px solid #444;padding:8px;text-align:left;}th{background-color:#222;}tr:nth-child(even){background-color:#111;}h2,h4{color:#0ff;}</style>
    <h2>📊 Droxion Dashboard</h2>
    <div>DAU: {{dau}} | WAU: {{wau}} | MAU: {{mau}}</div>
    <div>Peak Hour: {{peak}}</div>
    <div>Top Users: {{users}}</div>
    <div>Top Inputs: {{inputs}}</div>
    <div>Top Locations: {{locations}}</div>
    <hr><h4>Recent Logs</h4><table><tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
    {% for log in logs %}<tr><td>{{log["timestamp"]}}</td><td>{{log["user_id"]}}</td><td>{{log["action"]}}</td><td>{{log["input"]}}</td><td>{{log["ip"]}}</td><td>{{log["location"]}}</td></tr>{% endfor %}
    </table>
    """
    return render_template_string(html,
        dau=len(dau_set),
        wau=len(wau_set),
        mau=len(mau_set),
        peak=hour_count.most_common(1)[0][0] if hour_count else 0,
        users=dict(user_count.most_common(3)),
        inputs=dict(input_count.most_common(5)),
        locations=dict(location_count.most_common(3)),
        logs=logs[-100:]
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
