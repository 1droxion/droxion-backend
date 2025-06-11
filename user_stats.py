import os
import json
from flask import Flask, jsonify, request

app = Flask(__name__)

# Create folders and user database
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

USER_DB = os.path.join(os.getcwd(), "users.json")
if not os.path.exists(USER_DB):
    with open(USER_DB, "w") as f:
        json.dump({
            "demo_user": {
                "coins": 50,
                "plan": "Starter"
            }
        }, f)

# Get user data (with free VIP for "dhruv")
def get_user(user_id="demo_user"):
    if user_id == "dhruv":
        return {
            "coins": 999,
            "plan": "Pro"
        }
    with open(USER_DB, "r") as f:
        users = json.load(f)
    return users.get(user_id, {"coins": 0, "plan": "None"})

# ✅ Route to get full stats for a user
@app.route("/user-stats", methods=["GET"])
def user_stats():
    try:
        user_id = request.args.get("user_id", "demo_user")
        user = get_user(user_id)

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

if __name__ == "__main__":
    app.run(debug=True)
