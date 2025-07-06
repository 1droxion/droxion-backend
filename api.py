# ✅ Final api.py with OpenRouter fallback, voice, cards, and full CORS regex support

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time, re
from datetime import datetime
import pytz
import stripe

load_dotenv()
app = Flask(__name__)

# ✅ Allow all Vercel preview domains + main site
CORS(app, origins=[
    re.compile(r"^https:\/\/droxion-live-final.*\.vercel\.app$"),
    "https://www.droxion.com"
], supports_credentials=True)

# === ENV Vars ===
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

    suggestions = []
    cards = []
    reply = ""

    try:
        if "news" in prompt:
            news = requests.get("https://newsapi.org/v2/top-headlines", params={
                "country": "in" if "india" in prompt else "us",
                "apiKey": NEWS_API_KEY
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
            reply = f"Top News in {country}"
            suggestions = ["world news", "elon musk news", "crypto news"]

        elif "weather" in prompt:
            weather = requests.get("https://api.openweathermap.org/data/2.5/weather", params={
                "q": city or "Tupelo",
                "appid": WEATHER_API_KEY,
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
            fx = requests.get(f"https://v6.exchangerate-api.com/v6/{EXCHANGERATE_API_KEY}/latest/USD").json()
            inr = fx["conversion_rates"].get("INR")
            reply = f"💱 USD to INR: ₹{inr} — Live via ExchangeRate API"
            suggestions = ["usd to euro", "btc to usd"]

        elif "crypto" in prompt or "bitcoin" in prompt:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd").json()
            price = r['bitcoin']['usd']
            reply = f"🪙 Bitcoin Price: ${price} — via CoinGecko"
            suggestions = ["ethereum price", "dogecoin live", "crypto market"]

        elif "youtube" in prompt or "trending" in prompt:
            yt = requests.get("https://www.googleapis.com/youtube/v3/search", params={
                "part": "snippet",
                "q": "trending",
                "type": "video",
                "maxResults": 1,
                "key": YOUTUBE_API_KEY
            }).json()
            video = yt["items"][0]
            title = video["snippet"]["title"]
            video_id = video["id"]["videoId"]
            reply = f"🔥 YouTube Trending: {title}"
            cards.append(f"""
                <div class='p-2'>
                  <iframe width="300" height="200" src="https://www.youtube.com/embed/{video_id}" 
                    frameborder="0" allowfullscreen class='rounded-xl'></iframe>
                </div>
            """)
            suggestions = ["trending in India", "top music", "viral video"]

        elif "voice" in prompt or "speak" in prompt:
            text = "This is a test voice message from Droxion AI."
            audio_url = generate_elevenlabs_audio(text)
            reply = "🔊 Voice generated using ElevenLabs"
            cards.append(f"<audio controls src='{audio_url}' class='my-2'></audio>")
            suggestions = ["make it louder", "read this", "next voice"]

        elif "time" in prompt:
            reply = f"🕒 Time Now: {now.strftime('%I:%M %p')} ({now.strftime('%-m/%-d/%Y')})"
            suggestions = ["date today", "current time", "clock"]

        else:
            reply = openrouter_fallback(prompt)

    except Exception as e:
        reply = f"❌ Error: {str(e)}"

    return jsonify({"reply": reply, "cards": cards, "suggestions": suggestions})

def openrouter_fallback(prompt):
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openrouter/gpt-4",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload).json()
        return res['choices'][0]['message']['content']
    except:
        return "⚠️ No live result found. Try again with something more specific."

def generate_elevenlabs_audio(text):
    try:
        api_key = ELEVENLABS_API_KEY
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        body = {
            "model_id": "eleven_monolingual_v1",
            "text": text,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
        }
        voice_id = "21m00Tcm4TlvDq8ikWAM"
        res = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", headers=headers, json=body)
        filename = f"voice_{int(time.time())}.mp3"
        with open(filename, "wb") as f:
            f.write(res.content)
        return f"https://your-cdn.com/audio/{filename}"
    except:
        return ""

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
