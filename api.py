from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
import requests
import os
import openai

app = Flask(__name__)
CORS(app)

# --- Realtime Weather ---
@app.route('/realtime/weather', methods=['POST'])
def get_weather():
    data = request.get_json()
    city = data.get("city", "")
    if not city:
        return jsonify({"error": "City not provided"}), 400

    # MOCKED response - replace with your scraping logic later
    return jsonify({
        "city": city.title(),
        "temp": "31°C",
        "condition": "Sunny"
    })

# --- Realtime News ---
@app.route('/realtime/news', methods=['POST'])
def get_news():
    data = request.get_json()
    topic = data.get("topic", "")
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
    data = request.get_json()
    symbol = data.get("symbol", "")
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
    data = request.get_json()
    city = data.get("city", "").lower()
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

# --- Dummy /chat, /generate-image, /search-youtube ---
@app.route('/chat', methods=['POST'])
def chat():
    prompt = request.json.get("prompt", "")
    return jsonify({"reply": f"Echo: {prompt}"})

@app.route('/generate-image', methods=['POST'])
def generate_image():
    return jsonify({"image_url": "https://example.com/fake.jpg"})

@app.route('/search-youtube', methods=['POST'])
def youtube():
    return jsonify({"title": "Demo YouTube video", "url": "https://youtube.com"})

# --- App Launch ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)