from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
import requests
import os
import replicate
import openai

app = Flask(__name__)
CORS(app)

# Load keys
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

# --- Realtime Weather ---
@app.route('/realtime/weather', methods=['POST'])
def get_weather():
    city = request.json.get("city", "")
    if not city:
        return jsonify({"error": "City not provided"}), 400
    return jsonify({
        "city": city.title(),
        "temp": "31°C",
        "condition": "Sunny"
    })

# --- Realtime News ---
@app.route('/realtime/news', methods=['POST'])
def get_news():
    topic = request.json.get("topic", "")
    if not topic:
        return jsonify({"error": "Topic not provided"}), 400
    return jsonify({
        "headline": f"Latest update on {topic}",
        "source": "MockNews",
        "summary": f"This is a fake news preview about {topic} for testing.",
        "url": f"https://news.google.com/search?q={topic}"
    })

# --- Realtime Stock ---
@app.route('/realtime/stock', methods=['POST'])
def get_stock():
    symbol = request.json.get("symbol", "")
    if not symbol:
        return jsonify({"error": "Symbol not provided"}), 400
    return jsonify({
        "symbol": symbol.upper(),
        "price": "$891.22",
        "change": "+2.5%",
        "chart_url": f"https://finance.google.com/chart?q={symbol}"
    })

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
    tz_name = timezone_map.get(city, "UTC")
    time_now = datetime.now(pytz.timezone(tz_name)).strftime("%I:%M %p")
    return jsonify({
        "city": city.title(),
        "time": time_now
    })

# --- Chat (OpenRouter AI) ---
@app.route('/chat', methods=['POST'])
def chat():
    try:
        prompt = request.json.get("prompt", "")
        voiceMode = request.json.get("voiceMode", False)

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": prompt}]
        }

        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=data, headers=headers)
        result = response.json()
        reply = result["choices"][0]["message"]["content"]

        return jsonify({ "reply": reply })

    except Exception as e:
        print("Chat error:", str(e))
        return jsonify({ "reply": "❌ AI Error." })

# --- Image Generation using Replicate ---
@app.route('/generate-image', methods=['POST'])
def generate_image():
    try:
        prompt = request.json.get("prompt", "")
        output = replicate.run(
            "stability-ai/stable-diffusion:db21e45c84ed9171f63fdf4c4f6f3e5cbff9283c3e6c525e65e13c5c44f7d447",
            input={"prompt": prompt}
        )
        return jsonify({ "image_url": output[0] })
    except Exception as e:
        print("Image generation error:", str(e))
        return jsonify({ "error": str(e) }), 500

# --- YouTube Search ---
@app.route('/search-youtube', methods=['POST'])
def youtube():
    try:
        prompt = request.json.get("prompt", "")
        query = prompt.replace(" ", "+")
        yt_url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&q={query}&part=snippet&type=video&maxResults=1"
        r = requests.get(yt_url)
        j = r.json()
        if "items" in j and j["items"]:
            vid = j["items"][0]
            video_id = vid["id"]["videoId"]
            title = vid["snippet"]["title"]
            return jsonify({ "url": f"https://www.youtube.com/watch?v={video_id}", "title": title })
        return jsonify({ "error": "No video found" }), 404
    except Exception as e:
        return jsonify({ "error": str(e) }), 500

# --- App Launch ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)