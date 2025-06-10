import os
import json
from flask import Flask, jsonify

app = Flask(__name__)

# Public folder for video/image stats
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
if not os.path.exists(PUBLIC_FOLDER):
    os.makedirs(PUBLIC_FOLDER)

# Simple user database (JSON file)
USER_DB = os.path.join(os.getcwd(), "users.json")

# Ensure users.json exists
if not os.path.exists(USER_DB):
    with open(USER_DB, "w") as f:
        json.dump({
            "demo_user": {
                "coins": 50,
                "plan": "Starter"
            }
        }, f)

# Function to get user info
def get_user(user_id="demo_user"):
    with open(USER_DB, "r") as f:
        users = json.load(f)
    return users.get(user_id, {"coins": 0, "plan": "None"})

# Route to fetch user stats
@app.route("/user-stats", methods=["GET"])
def user_stats():
    try:
        user = get_user()  # Use default demo_user for now

        plan = {
            "name": user.get("plan", "Starter"),
            "videoLimit": 5,
            "imageLimit": 20,
            "autoLimit": 10
        }

        videos = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
        images = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".png") and "styled" in f]
        auto_generates = 6  # Optional: replace with real logic

        stats = {
            "coins": user.get("coins", 0),
            "videosThisMonth": len(videos),
            "imagesThisMonth": len(images),
            "autoGenerates": auto_generates,
            "plan": plan
        }

        return jsonify(stats)

    except Exception as e:
        print("❌ Stats Error:", e)
        return jsonify({"error": "Could not fetch stats"}), 500
