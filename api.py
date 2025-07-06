from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time, re
from datetime import datetime
import pytz
import stripe

# === Load env vars ===
load_dotenv()
app = Flask(__name__)

# === Allow frontend
CORS(app, origins=[
    re.compile(r"^https:\/\/droxion-live-final.*\.vercel\.app$"),
    "https://www.droxion.com"
], supports_credentials=True)

# === ENV Vars
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
EXCHANGERATE_API_KEY = os.getenv("EXCHANGERATE_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

stripe.api_key = STRIPE_SECRET_KEY

@app.route("/chat", methods=["POST"])
def chat():
    prompt = request.json.get("prompt", "").lower()
    user_id = request.json.get("user_id", "anon")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    city, country = get_location_from_ip(ip)
    now = datetime.now(pytz.timezone("Asia/Kolkata"))

    reply = ""
    cards = []
    suggestions = []

    try:
        if "news" in prompt:
            news = requests.get("https://newsapi.org/v2/top-headlines", params={
                "country": "in" if "india" in prompt else "us",
                "apiKey": NEWS_API_KEY
            }).json()
            articles = news.get("articles", [])[:3]
            card_items = []
            for article in articles:
                card_items.append(f"""
                <div class='border border-gray-600 p-2 rounded-xl w-[300px]'>
                  <div class='text-sm font-bold'>📰 {article['title']}</div>
                  <div class='text-xs text-gray-400 mb-1'>{article['source']['name']}</div>
                  <img src='{article['urlToImage']}' class='w-full h-40 object-cover my-2 rounded-lg'/>
                  <a href='{article['url']}' class='text-blue-400 underline'>Read Full</a>
                </div>
                """)
            cards.append(f"<div class='flex gap-3 flex-wrap'>{''.join(card_items)}</div>")
            reply = f"Top News in {country}"
            suggestions = ["world news", "elon musk news", "crypto news"]

        elif "weather" in prompt:
            res = requests.get("https://api.openweathermap.org/data/2.5/weather", params={
                "q": city or "New York",
                "appid": WEATHER_API_KEY,
                "units": "metric"
            })
            if res.ok:
                data = res.json()
                desc = data['weather'][0]['description']
                temp = data['main']['temp']
                reply = f"🌤️ Weather in {city}: {temp}°C, {desc}"
                suggestions = ["7 day forecast", "weather tomorrow"]
            else:
                reply = "❌ Error: Weather info not available"

        elif "stock" in prompt or "tesla" in prompt:
            res = requests.get("https://query1.finance.yahoo.com/v7/finance/quote", params={"symbols": "TSLA"})
            if res.ok:
                data = res.json()
                quote = data['quoteResponse']['result'][0]
                price = quote['regularMarketPrice']
                change = quote['regularMarketChangePercent']
                cards.append(f"""
                <div class='flex gap-3 flex-wrap'>
                  <div class='border border-gray-600 p-3 rounded-xl w-[300px]'>
                    <div class='text-sm font-bold'>📈 Tesla Stock: ${price} ({change:.2f}%)</div>
                    <div class='text-xs text-gray-400'>Yahoo Finance</div>
                  </div>
                </div>
                """)
                reply = "Here's the latest Tesla stock info."
                suggestions = ["apple stock", "meta stock", "microsoft stock"]
            else:
                reply = "❌ Error: Stock data not available"

        elif "usd" in prompt and ("inr" in prompt or "to" in prompt):
            fx = requests.get(f"https://v6.exchangerate-api.com/v6/{EXCHANGERATE_API_KEY}/latest/USD").json()
            inr = fx["conversion_rates"].get("INR")
            reply = f"💱 USD to INR: ₹{inr} — Live via ExchangeRate API"
            suggestions = ["usd to euro", "btc to usd"]

        elif "crypto" in prompt or "bitcoin" in prompt:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
            if r.ok:
                data = r.json()
                price = data.get('bitcoin', {}).get('usd')
                reply = f"🪙 Bitcoin Price: ${price} — via CoinGecko" if price else "❌ Error: Price not available"
                suggestions = ["ethereum price", "dogecoin live", "crypto market"]
            else:
                reply = "❌ Error: Crypto data failed"

        elif "youtube" in prompt or "trending" in prompt:
            yt = requests.get("https://www.googleapis.com/youtube/v3/search", params={
                "part": "snippet",
                "q": "trending",
                "type": "video",
                "maxResults": 1,
                "key": YOUTUBE_API_KEY
            }).json()
            if yt.get("items"):
                video = yt["items"][0]
                title = video["snippet"]["title"]
                video_id = video["id"]["videoId"]
                reply = f"🔥 YouTube Trending: {title}"
                cards.append(f"""
                <div class='flex gap-3 flex-wrap'>
                  <div class='border border-gray-600 p-2 rounded-xl w-[300px]'>
                    <iframe width="100%" height="180" src="https://www.youtube.com/embed/{video_id}" 
                      frameborder="0" allowfullscreen class='rounded-lg'></iframe>
                  </div>
                </div>
                """)
                suggestions = ["trending in India", "top music", "viral video"]
            else:
                reply = "⚠️ No trending videos found."

        elif "time" in prompt:
            reply = f"🕒 Time Now: {now.strftime('%I:%M %p')} ({now.strftime('%-m/%-d/%Y')})"
            suggestions = ["date today", "current time", "clock"]

        else:
            reply = openrouter_fallback(prompt)

    except Exception as e:
        reply = f"❌ Error: {str(e)}"

    if not reply:
        reply = "⚠️ No live result found. Try again with something more specific."

    return jsonify({"reply": reply, "cards": cards, "suggestions": suggestions})

def openrouter_fallback(prompt):
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "mistral-7b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        data = res.json()
        return data['choices'][0]['message']['content']
    except:
        return "⚠️ No live result found. Try again with something more specific."

def get_location_from_ip(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip.split(',')[0].strip()}").json()
        return res.get("city", "Tupelo"), res.get("country", "USA")
    except:
        return "Tupelo", "USA"

@app.route("/")
def home():
    return "✅ Droxion Backend Live"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
