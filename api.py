from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# Chat route
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    return jsonify({"reply": f"Echo: {user_message}"})

# Image generator route
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json()
    prompt = data.get("prompt", "")
    return jsonify({"image": f"https://fakeimg.pl/600x400/?text={prompt.replace(' ', '+')}"})

# YouTube search mock route
@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    data = request.get_json()
    query = data.get("query", "")
    return jsonify({"title": f"YouTube result for {query}", "url": f"https://youtube.com/results?q={query}"})

# -----------------------------
# 🔥 NEW: Real-time routes below
# -----------------------------

@app.route("/realtime/weather", methods=["POST"])
def realtime_weather():
    data = request.get_json()
    city = data.get("city", "")
    return jsonify({
        "city": city.title(),
        "temp": "29°C",
        "condition": "Partly Cloudy"
    })

@app.route("/realtime/news", methods=["POST"])
def realtime_news():
    data = request.get_json()
    topic = data.get("topic", "")
    return jsonify({
        "topic": topic.title(),
        "headlines": [
            f"{topic.title()} makes headlines again!",
            f"Top story: {topic.title()} update",
            f"Why {topic.title()} is trending now"
        ]
    })

@app.route("/realtime/stock", methods=["POST"])
def realtime_stock():
    data = request.get_json()
    symbol = data.get("symbol", "")
    return jsonify({
        "symbol": symbol.upper(),
        "price": "$123.45",
        "change": "+2.5%"
    })

@app.route("/realtime/time", methods=["POST"])
def realtime_time():
    data = request.get_json()
    city = data.get("city", "")
    return jsonify({
        "city": city.title(),
        "time": "7:15 PM",
        "date": "July 14, 2025"
    })

# -----------------------
# Run app
# -----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)