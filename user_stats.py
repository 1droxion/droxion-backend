import os
import json
from flask import Flask, jsonify

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

# Always return "dhruv" as free Pro user
def get_user():
    return {
        "coins": 999,
        "plan": "Pro"
    }

@app.route("/user-stats", methods=["GET"])
def user_stats():
    try:
        user = get_user()

        plan = {
            "name": user.get("plan", "Starter"),
            "videoLimit": 5,
            "imageLimit": 20,
            "autoLimit": 10
        }

        videos = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
        images = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".png") and "styled" in f]
        auto_generates = 6  # optional logic

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
