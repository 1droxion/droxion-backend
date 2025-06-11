from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re
import sys
import logging
import time
import datetime
import ast
import threading
import json
from engine.live_engine import run_forever  # ✅ Live simulation logic

# ✅ Logging setup
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# ✅ Load .env variables
load_dotenv()

app = Flask(__name__)

# ✅ Allow frontend origin (Droxion)
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

# ✅ Public folder
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ Coin + usage stats route
@app.route("/user-stats", methods=["GET"])
def user_stats():
    try:
        plan = {
            "name": "Starter",
            "videoLimit": 5,
            "imageLimit": 20,
            "autoLimit": 10
        }
        videos = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
        images = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".png") and "styled" in f]
        auto_generates = 6
        stats = {
            "credits": 18,
            "videosThisMonth": len(videos),
            "imagesThisMonth": len(images),
            "autoGenerates": auto_generates,
            "plan": plan
        }
        return jsonify(stats)
    except Exception as e:
        print("❌ Stats Error:", e)
        return jsonify({"error": "Could not fetch stats"}), 500

# ✅ Image generator
@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        headers = {
            "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
            "Content-Type": "application/json"
        }
        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            "input": {
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 30,
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False
            }
        }
        create = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        if create.status_code != 201:
            return jsonify({"error": "Failed to create prediction", "details": create.json()}), 500

        prediction = create.json()
        get_url = prediction.get("urls", {}).get("get")
        while True:
            poll = requests.get(get_url, headers=headers)
            poll_result = poll.json()
            status = poll_result.get("status")
            if status == "succeeded":
                return jsonify({"image_url": poll_result.get("output")})
            if status == "failed":
                return jsonify({"error": "Prediction failed"}), 500
            time.sleep(1)
    except Exception as e:
        print("❌ Image Generation Error:", e)
        return jsonify({"error": f"Exception: {str(e)}"}), 500

# ✅ AI Chat route
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        api_key = os.getenv("OPENROUTER_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are an assistant powered by Droxion."},
                {"role": "user", "content": prompt}
            ]
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        result = response.json()

        if response.status_code != 200:
            return jsonify({"reply": f"❌ OpenRouter Error: {result.get('message', 'Unknown error')}"}), 400
        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        print("❌ Chat Exception:", e)
        return jsonify({"reply": f"Error: {str(e)}"}), 500

# ✅ Event logging
@app.route("/track", methods=["POST"])
def track_event():
    try:
        data = request.json
        data["timestamp"] = str(datetime.datetime.utcnow())
        with open("analytics.log", "a") as f:
            f.write(str(data) + "\n")
        return jsonify({"status": "ok"})
    except Exception as e:
        print("❌ Track error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/analytics", methods=["GET"])
def get_analytics():
    try:
        logs = []
        if os.path.exists("analytics.log"):
            with open("analytics.log", "r") as f:
                for line in f:
                    try:
                        logs.append(ast.literal_eval(line.strip()))
                    except:
                        pass
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Fixed route for Live Earth simulation
@app.route("/live-earth", methods=["GET"])
def live_earth():
    try:
        with open("world_state.json", "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        print("❌ World State Error:", e)
        return jsonify({"error": "Could not fetch world state"}), 500

# ✅ Start the AI simulation thread
threading.Thread(target=run_forever, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
