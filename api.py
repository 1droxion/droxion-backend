from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
import requests
import os
import replicate

app = Flask(__name__)
CORS(app)

# Load environment keys
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# --- Realtime Weather ---
@app.route('/realtime/weather', methods=['POST'])
def get_weather():
    city = request.json.get("city", "")
    return jsonify({
        "city": city.title(),
        "temp": "31°C",
        "condition": "Sunny"
    }) if city else jsonify({"error": "City missing"}), 400

# --- Realtime News ---
@app.route('/realtime/news', methods=['POST'])
def get_news():
    topic = request.json.get("topic", "")
    return jsonify({
        "headline": f"News about {topic}",
        "source": "MockNews",
        "summary": f"This is a news preview about {topic}.",
        "url": f"https://news.google.com/search?q={topic}"
    }) if topic else jsonify({"error": "Topic missing"}), 400

# --- Realtime Stock ---
@app.route('/realtime/stock', methods=['POST'])
def get_stock():
    symbol = request.json.get("symbol", "")
    return jsonify({
        "symbol": symbol.upper(),
        "price": "$891.22",
        "change": "+2.5%",
        "chart_url": f"https://finance.google.com/chart?q={symbol}"
    }) if symbol else jsonify({"error": "Symbol missing"}), 400

# --- Realtime Time ---
@app.route('/realtime/time', methods=['POST'])
def get_time():
    city = request.json.get("city", "").lower()
    timezone_map = {
        "new york": "America/New_York",
        "los angeles": "America/Los_Angeles",
        "london": "Europe/London",
        "mumbai": "Asia/Kolkata",
        "tokyo": "Asia/Tokyo",
        "sydney": "Australia/Sydney"
    }
    tz = timezone_map.get(city, "UTC")
    now = datetime.now(pytz.timezone(tz)).strftime("%I:%M %p")
    return jsonify({ "city": city.title(), "time": now })

# --- AI Chat with OpenRouter ---
@app.route('/chat', methods=['POST'])
def chat():
    try:
        prompt = request.json.get("prompt", "")
        if not prompt:
            return jsonify({"reply": "❌ No prompt provided."})

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openai/gpt-4o",  # You can switch to mistralai/mixtral if needed
            "messages": [{"role": "user", "content": prompt}]
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)
        out = res.json()

        if "choices" in out:
            reply = out["choices"][0]["message"]["content"]
            return jsonify({ "reply": reply })
        else:
            print("Chat error response:", out)
            return jsonify({ "reply": "❌ AI Error." })

    except Exception as e:
        print("Chat error:", str(e))
        return jsonify({ "reply": "❌ AI Error." })

# --- Image Generation with Replicate ---
@app.route('/generate-image', methods=['POST'])
def generate_image():
    try:
        prompt = request.json.get("prompt", "")
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        output = replicate.run(
            "stability-ai/stable-diffusion:db21e45c84ed9171f63fdf4c4f6f3e5cbff9283c3e6c525e65e13c5c44f7d447",
            input={"prompt": prompt}
        )

        if isinstance(output, list) and output and output[0].startswith("http"):
            return jsonify({ "image_url": output[0] })
        else:
            print("Replicate output invalid:", output)
            return jsonify({ "error": "❌ No image returned from model" })

    except Exception as e:
        print("Image error:", str(e))
        return jsonify({ "error": str(e) }), 500

# --- YouTube Search ---
@app.route('/search-youtube', methods=['POST'])
def youtube():
    try:
        prompt = request.json.get("prompt", "")
        if not prompt:
            return jsonify({ "error": "Prompt missing" }), 400

        q = prompt.replace(" ", "+")
        url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&q={q}&part=snippet&type=video&maxResults=1"
        r = requests.get(url).json()

        if "items" in r and r["items"]:
            vid = r["items"][0]
            video_id = vid["id"]["videoId"]
            title = vid["snippet"]["title"]
            return jsonify({ "url": f"https://www.youtube.com/watch?v={video_id}", "title": title })

        print("YT response:", r)
        return jsonify({ "error": "No video found" }), 404

    except Exception as e:
        print("YouTube error:", str(e))
        return jsonify({ "error": "YouTube failed" }), 500

# --- Launch ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)