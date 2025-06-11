from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json
import logging
import sys
import time
import datetime
import ast
import threading
from engine.live_engine import run_forever  # ✅ Optional simulation engine

# Logging
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
load_dotenv()

app = Flask(__name__)
CORS(app)

# ✅ Public folder for generated media
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ World Stats (optional fallback)
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

# ✅ New route: return entire universe timeline
@app.route("/world-state", methods=["GET"])
def world_state():
    try:
        with open("world_state.json", "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        print("❌ World State Error:", e)
        return jsonify({"error": "Could not fetch world state"}), 500

# ✅ Optional analytics tracker
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

# ✅ Optional simulation background engine
threading.Thread(target=run_forever, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
