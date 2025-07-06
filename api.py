from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
import pytz
import stripe

load_dotenv()
app = Flask(__name__)

# ✅ Fixed: Allow both main + Vercel preview URL
CORS(app, origins=[
    "https://droxion-live-final.vercel.app",
    "https://droxion-live-final-cuhb-git-main-suchitbhai-g-patel.vercel.app",
    "https://www.droxion.com"
], supports_credentials=True)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

stripe.api_key = STRIPE_SECRET_KEY

@app.route("/realtime", methods=["POST"])
def realtime():
    prompt = request.json.get("prompt", "").lower()
    user_id = request.json.get("user_id", "anon")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    city, country = get_location_from_ip(ip)
    now = datetime.now(pytz.timezone("Asia/Kolkata"))

    suggestions = []
    cards = []
    reply = ""

    if "news" in prompt:
        news = requests.get("https://newsapi.org/v2/top-headlines", params={
            "country": "in" if "india" in prompt else "us",
            "apiKey": os.getenv("NEWS_API_KEY")
        }).json()
        for article in news.get("articles", [])[:3]:
            cards.append(f"""
            <div class='border border-gray-600 p-3 rounded-xl my-2 max-w-xl'>
              <div class='text-sm font-bold'>📰 {article['title']}</div>
              <div class='text-xs text-gray-400 mb-1'>{article['source']['name']}</div>
              <img src='{article['urlToImage']}' class='w-full max-w-sm my-2 rounded-lg'/>
              <a href='{article['url']}' class='text-blue-400 underline'>Read Full</a>
            </div>
            """)
        reply = f"Top News from Google News in {country}:"
        suggestions = ["world news", "elon musk news", "crypto news"]

    elif "weather" in prompt:
        weather = requests.get("https://api.openweathermap.org/data/2.5/weather", params={
            "q": city or "Tupelo",
            "appid": os.getenv("WEATHER_API_KEY"),
            "units": "metric"
        }).json()
        desc = weather['weather'][0]['description']
        temp = weather['main']['temp']
        reply = f"🌤️ Weather in {city or country}: {temp}°C, {desc}"
        suggestions = ["7 day forecast", "weather tomorrow"]

    elif "stock" in prompt or "tesla" in prompt:
        data = requests.get("https://query1.finance.yahoo.com/v7/finance/quote", params={"symbols": "TSLA"}).json()
        quote = data['quoteResponse']['result'][0]
        price = quote['regularMarketPrice']
        change = quote['regularMarketChangePercent']
        reply = f"📈 Tesla Stock: ${price} ({change:.2f}%) — Yahoo Finance"
        suggestions = ["apple stock", "meta stock", "microsoft stock"]

    elif "usd" in prompt and ("inr" in prompt or "to" in prompt):
        fx = requests.get("https://v6.exchangerate-api.com/v6/YOUR_API_KEY/latest/USD").json()
        inr = fx["conversion_rates"].get("INR")
        reply = f"💱 USD to INR: ₹{inr} (Live) — XE.com"
        suggestions = ["usd to euro", "btc to usd"]

    elif "time" in prompt:
        reply = f"🕒 Time Now: {now.strftime('%I:%M %p')} ({now.strftime('%-m/%-d/%Y')})"

    else:
        reply = "I couldn't find a live preview, but you can try searching more directly."

    return jsonify({"reply": reply, "cards": cards, "suggestions": suggestions})

def get_location_from_ip(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip.split(',')[0].strip()}").json()
        return res.get("city", "Tupelo"), res.get("country", "USA")
    except:
        return "Tupelo", "USA"

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
