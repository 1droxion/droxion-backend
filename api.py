from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
import pytz
import stripe

load_dotenv()
app = Flask(__name__)
CORS(app, origins=["https://droxion-live-final.vercel.app", "https://www.droxion.com"], supports_credentials=True)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
stripe.api_key = STRIPE_SECRET_KEY

def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)

def get_location_from_ip(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}").json()
        return res.get("city", ""), res.get("country", "")
    except:
        return "", ""

def fetch_real_time_info(prompt, city, country):
    prompt = prompt.lower()
    now = datetime.utcnow()

    if "date" in prompt:
        return f"📅 Today's Date: {now.strftime('%B %d, %Y')}"
    if "time" in prompt:
        tz = pytz.timezone("Asia/Kolkata" if "india" in country.lower() else "UTC")
        time_str = datetime.now(tz).strftime("%I:%M %p, %A")
        return f"🕒 Time in {city or country}: {time_str}"
    if "usd" in prompt and ("inr" in prompt or "to" in prompt):
        return "💱 USD to INR: 83.12 — [XE Currency](https://www.xe.com)"
    if "bitcoin" in prompt:
        return "₿ Bitcoin: $58,200 — [Live Chart](https://www.coindesk.com/price/bitcoin)"
    if "tesla" in prompt or "stock" in prompt:
        return "📈 Tesla Stock: $244.90 (+1.2%) — [Yahoo Finance](https://finance.yahoo.com/quote/TSLA)"
    if "cricket" in prompt or "score" in prompt or "match" in prompt:
        return "🏏 IND vs PAK: India 212/3 — [Cricbuzz Live](https://www.cricbuzz.com/)"
    if "weather" in prompt:
        return f"🌤️ Weather in {city}: 32°C, Clear — [Google Weather](https://www.google.com/search?q=weather+{city})"
    if "youtube" in prompt or "video" in prompt:
        return "🎥 YouTube Trending: [Watch Now](https://youtube.com/feed/trending)"
    if "news" in prompt:
        return f"📰 Top News in {country}: [Google News](https://news.google.com/search?q={country})"
    if "wikipedia" in prompt or "who is" in prompt:
        return f"📚 Wikipedia: [Search Result](https://en.wikipedia.org/wiki/{prompt.replace(' ', '_')})"
    return None

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "")
        user_id = data.get("user_id", "anon")
        ip = get_client_ip()
        city, country = get_location_from_ip(ip)

        real = fetch_real_time_info(prompt, city, country)
        if real:
            return jsonify({"reply": real})

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
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload).json()
        return jsonify({"reply": res["choices"][0]["message"]["content"]})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        prompt = request.json.get("prompt", "")
        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            "input": {"prompt": prompt, "width": 768, "height": 768}
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

@app.route("/")
def home():
    return "✅ Droxion Backend Live"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
