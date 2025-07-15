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

# ENV
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

stripe.api_key = STRIPE_SECRET_KEY
LOG_FILE = "user_logs.json"
PAID_USER_FILE = "users.json"

# Location
def get_location_from_ip(ip):
    try:
        main_ip = ip.split(",")[0].strip()
        res = requests.get(f"http://ip-api.com/json/{main_ip}")
        data = res.json()
        return f"{data['city']}, {data['countryCode']}" if data["status"] == "success" else ""
    except: return ""

def get_client_ip(): return request.headers.get("X-Forwarded-For", request.remote_addr)

def log_user_action(user_id, action, input_text, ip):
    now = datetime.utcnow().isoformat() + "Z"
    location = get_location_from_ip(ip)
    new_entry = {
        "timestamp": now, "user_id": user_id,
        "action": action, "input": input_text,
        "ip": ip, "location": location
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try: logs = json.load(open(LOG_FILE))
        except: logs = []
    logs.append(new_entry)
    json.dump(logs, open(LOG_FILE, "w"), indent=2)

def load_paid_users():
    return json.load(open(PAID_USER_FILE)) if os.path.exists(PAID_USER_FILE) else {}

def save_paid_users(data): json.dump(data, open(PAID_USER_FILE, "w"), indent=2)

@app.route("/")
def home(): return "✅ Droxion Backend is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt: return jsonify({"reply": "❗ Prompt required."}), 400
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
        if not prompt: return jsonify({"error": "Prompt required"}), 400
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
            if poll["status"] == "succeeded": return jsonify({"image_url": poll["output"]})
            elif poll["status"] == "failed": return jsonify({"error": "Image generation failed"}), 500
            time.sleep(1)
    except Exception as e:
        return jsonify({"error": f"Image error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "")
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet", "q": prompt,
            "type": "video", "maxResults": 1,
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

@app.route("/realtime/time", methods=["POST"])
def get_time():
    data = request.get_json()
    city = data.get("city", "").lower()
    tz_map = {
        "new york": "America/New_York",
        "london": "Europe/London",
        "mumbai": "Asia/Kolkata",
        "tokyo": "Asia/Tokyo",
        "sydney": "Australia/Sydney"
    }
    tz_name = tz_map.get(city, "UTC")
    time_now = datetime.now(pytz.timezone(tz_name)).strftime("%I:%M %p")
    return jsonify({"city": city.title(), "time": time_now})

@app.route("/realtime/weather", methods=["POST"])
def get_weather():
    city = request.json.get("city", "")
    return jsonify({"city": city.title(), "temp": "31°C", "condition": "Sunny"})

@app.route("/realtime/news", methods=["POST"])
def get_news():
    topic = request.json.get("topic", "")
    return jsonify({
        "headline": f"Update on {topic}",
        "source": "MockNews",
        "summary": f"News preview about {topic}",
        "url": f"https://news.google.com/search?q={topic}"
    })

@app.route("/realtime/stock", methods=["POST"])
def get_stock():
    symbol = request.json.get("symbol", "")
    return jsonify({
        "symbol": symbol.upper(),
        "price": "$891.22",
        "change": "+2.5%",
        "chart_url": f"https://finance.google.com/chart?q={symbol}"
    })

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

@app.route("/check-paid", methods=["POST"])
def check_paid():
    data = request.json
    user_id = data.get("user_id", "")
    users = load_paid_users()
    return jsonify({"paid": users.get(user_id, {}).get("paid", False)})

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return f"❌ Webhook error: {str(e)}", 400
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id", "")
        users = load_paid_users()
        users[user_id] = {"paid": True, "date": datetime.utcnow().isoformat()}
        save_paid_users(users)
    return jsonify(success=True)

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN: return "❌ Unauthorized", 401
    days = int(request.args.get("days", 7))
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    dau, wau, mau = set(), set(), set()
    hour_count, input_count, user_count, loc_count = Counter(), Counter(), Counter(), Counter()
    logs = json.load(open(LOG_FILE)) if os.path.exists(LOG_FILE) else []
    for l in logs:
        try:
            ts = parser.isoparse(l["timestamp"]).replace(tzinfo=pytz.UTC)
            if (now - ts).days <= days:
                uid = l.get("user_id", "anon")
                dau.add(uid); wau.add(uid); mau.add(uid)
                hour_count[ts.hour] += 1
                input_count[l.get("input", "")] += 1
                user_count[uid] += 1
                loc_count[l.get("location", "")] += 1
        except: continue
    html = """<style>body{background:#000;color:#fff;font-family:Arial}table{border-collapse:collapse;width:100%}th,td{border:1px solid #333;padding:6px}</style>
    <h2>Droxion Dashboard</h2>
    <div>DAU: {{dau}} | WAU: {{wau}} | MAU: {{mau}}</div>
    <div>Peak: {{peak}}</div>
    <table><tr><th>User</th><th>Action</th><th>Input</th><th>Time</th><th>IP</th><th>Location</th></tr>
    {% for log in logs %}<tr><td>{{log.user_id}}</td><td>{{log.action}}</td><td>{{log.input}}</td><td>{{log.timestamp}}</td><td>{{log.ip}}</td><td>{{log.location}}</td></tr>{% endfor %}
    </table>
    """
    return render_template_string(html,
        dau=len(dau), wau=len(wau), mau=len(mau),
        peak=hour_count.most_common(1)[0][0] if hour_count else 0,
        logs=logs[-100:]
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))