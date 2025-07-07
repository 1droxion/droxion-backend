
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

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
EXCHANGERATE_API_KEY = os.getenv("EXCHANGERATE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
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

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        user_id = data.get("user_id", "anonymous")
        ip = get_client_ip()
        log_user_action(user_id, "message", prompt, ip)

        reply, cards, suggestions = "", [], []

        p = prompt.lower()

        if "time" in p or "date" in p:
            now = datetime.now(pytz.timezone("Asia/Kolkata"))
            reply = f"🕒 Time Now: {now.strftime('%I:%M %p')} ({now.strftime('%-m/%-d/%Y')})"
            suggestions = ["weather", "current time", "news"]

        elif "weather" in p:
            city = "New York"
            for w in prompt.split():
                if w.istitle():
                    city = w
            res = requests.get("https://api.openweathermap.org/data/2.5/weather", params={
                "q": city,
                "appid": WEATHER_API_KEY,
                "units": "metric"
            }).json()
            if res.get("main"):
                desc = res["weather"][0]["description"].title()
                temp = res["main"]["temp"]
                cards.append(f"<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>🌦️ Weather in {city}</div><div class='text-sm mt-1'>{desc}, {temp}°C</div></div>")
                reply = f"Weather in {city}"
                suggestions = ["7 day forecast", "weather tomorrow"]

        elif "news" in p:
            country = "in" if "india" in p else "us"
            res = requests.get("https://newsapi.org/v2/top-headlines", params={
                "country": country,
                "apiKey": NEWS_API_KEY
            }).json()
            for article in res.get("articles", [])[:3]:
                cards.append(f"<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>📰 {article['title']}</div><div class='text-xs text-gray-400 mb-1'>{article['source']['name']}</div><img src='{article['urlToImage']}' class='w-full h-40 object-cover my-2 rounded-lg'/><a href='{article['url']}' class='text-blue-400 underline'>Read Full</a></div>")
            reply = "Top News"
            suggestions = ["crypto news", "tech news", "elon musk news"]

        elif "usd to inr" in p:
            r = requests.get(f"https://v6.exchangerate-api.com/v6/{EXCHANGERATE_API_KEY}/latest/USD").json()
            rate = r.get("conversion_rates", {}).get("INR")
            reply = f"💱 USD to INR: ₹{rate}"
            suggestions = ["usd to euro", "btc to usd"]

        elif "bitcoin" in p or "crypto" in p:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd").json()
            price = r.get("bitcoin", {}).get("usd")
            reply = f"🪙 Bitcoin Price: ${price}"
            suggestions = ["ethereum price", "crypto market"]

        elif "stock" in p or "tesla" in p:
            r = requests.get("https://query1.finance.yahoo.com/v7/finance/quote", params={"symbols": "TSLA"}).json()
            q = r.get("quoteResponse", {}).get("result", [{}])[0]
            cards.append(f"<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>📈 {q.get('longName', 'Tesla')}: ${q.get('regularMarketPrice')}</div><div class='text-xs text-gray-400'>TSLA • {q.get('marketState')}</div></div>")
            reply = "Tesla Stock Info"
            suggestions = ["apple stock", "meta stock"]

        elif "score" in p or "match" in p:
            cards.append("<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>🏏 India vs Pakistan</div><div class='text-sm mt-1'>India: 298/7 (50) • Pak: 145/3 (32)</div></div>")
            reply = "Live Match Score"
            suggestions = ["india match", "world cup", "live football"]

        elif p.startswith("google:") or p.startswith("search:"):
            q = p.split(":", 1)[1].strip()
            res = requests.get("https://www.googleapis.com/customsearch/v1", params={
                "q": q,
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_CSE_ID
            }).json()
            if res.get("items"):
                top = res["items"][0]
                cards.append(f"<div class='border border-gray-600 p-3 rounded-xl max-w-xs'><div class='font-bold text-sm'>{top.get('title')}</div><div class='text-xs text-gray-400'>{top.get('displayLink')}</div><p class='text-sm my-1'>{top.get('snippet')}</p><a href='{top.get('link')}' class='text-blue-400 underline'>Visit</a></div>")
                reply = f"Search result for: {q}"
                suggestions = ["wikipedia", "youtube", "openai"]

        else:
            # fallback to GPT
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
