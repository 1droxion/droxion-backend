from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time, re
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

# Required API KEYS only
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
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        except:
            logs = []
    logs.append({
        "timestamp": now,
        "user_id": user_id,
        "action": action,
        "input": input_text,
        "ip": ip,
        "location": location
    })
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

@app.route("/")
def home():
    return "✅ Droxion Flask Backend (Scraping-based) is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip().lower()
        user_id = data.get("user_id", "anon")
        ip = get_client_ip()
        log_user_action(user_id, "message", prompt, ip)

        cards, suggestions = [], []
        reply = ""

        if "time" in prompt or "date" in prompt:
            now = datetime.now(pytz.timezone("Asia/Kolkata"))
            reply = f"🕒 Time Now: {now.strftime('%I:%M %p')} ({now.strftime('%-m/%-d/%Y')})"
            suggestions = ["weather", "current time", "news"]

        elif "weather" in prompt:
            city = "New York"
            for w in prompt.split():
                if w.istitle():
                    city = w
            wttr = requests.get(f"https://wttr.in/{city}?format=3").text
            reply = wttr
            suggestions = ["weather tomorrow", "7 day forecast"]

        elif "news" in prompt:
            feed = requests.get("https://news.google.com/rss").text
            items = re.findall(r"<title>(.*?)</title>", feed)[2:5]
            for title in items:
                cards.append(f"<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>📰 {title}</div></div>")
            reply = "Top Headlines"
            suggestions = ["tech news", "crypto news"]

        elif "usd to inr" in prompt:
            html = requests.get("https://www.x-rates.com/calculator/?from=USD&to=INR&amount=1").text
            rate = re.search(r'1 USD = ([\\d.]+) Indian Rupee', html)
            reply = f"💱 USD to INR: ₹{rate.group(1) if rate else '85.4'}"
            suggestions = ["usd to euro", "btc to usd"]

        elif "bitcoin" in prompt or "crypto" in prompt:
            html = requests.get("https://www.coingecko.com/en/coins/bitcoin").text
            price = re.search(r'"price">\\$(\\d+,?\\d+)', html)
            reply = f"🪙 Bitcoin Price: ${price.group(1) if price else 'Unknown'}"
            suggestions = ["ethereum price", "crypto market"]

        elif "stock" in prompt or "tesla" in prompt:
            html = requests.get("https://finance.yahoo.com/quote/TSLA/").text
            match = re.search(r'"regularMarketPrice":{"raw":([\d.]+)', html)
            price = match.group(1) if match else "Unknown"
            cards.append(f"<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>📈 Tesla Stock: ${price}</div></div>")
            reply = "Tesla Stock Info"
            suggestions = ["apple stock", "meta stock"]

        elif "score" in prompt or "match" in prompt:
            cards.append("<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>🏏 India vs Pakistan</div><div class='text-sm mt-1'>India: 298/7 (50) • Pak: 145/3 (32)</div></div>")
            reply = "Live Match Score"
            suggestions = ["india match", "live cricket", "football today"]

        else:
            # fallback to OpenAI GPT
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

        return jsonify({"reply": reply, "cards": cards, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
