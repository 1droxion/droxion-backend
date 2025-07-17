from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import requests
import datetime
import pytz
import os
import json
import time

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MEMORY_FILE = "memory.json"

# ----------------- MEMORY LOGIC ------------------
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w") as f:
            json.dump({}, f)
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def update_user_memory(user_id, goal):
    memory = load_memory()
    if user_id not in memory:
        memory[user_id] = {"goals": []}
    if goal not in memory[user_id]["goals"]:
        memory[user_id]["goals"].append(goal)
    save_memory(memory)

# ------------------ CHAT ROUTE -------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "").strip()
    user_id = data.get("user_id", "anonymous")

    memory = load_memory()
    user_memory = memory.get(user_id, {"goals": []})
    lower = prompt.lower()

    # Save new goal to memory
    if lower.startswith("remember") or "my goal is" in lower:
        goal = prompt.replace("remember", "").replace("my goal is", "").strip()
        update_user_memory(user_id, goal)
        return jsonify({"reply": f"✅ Got it. I’ll remember: *{goal}*."})

    # Inject memory into system prompt
    goals = user_memory.get("goals", [])
    system_context = "This user has the following goals:\n" + "\n".join(f"- {g}" for g in goals) if goals else "No saved goals yet."

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"You are a helpful AI assistant.\n{system_context}"},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"⚠️ Error: {str(e)}"

    return jsonify({"reply": reply})


# ------------------ IMAGE GENERATION -------------------
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt")
    try:
        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "db21e45a-df6d-4845-90c5-6e1f01b16f3f",
                "input": {"prompt": prompt}
            }
        )
        result = response.json()
        prediction_url = result.get("urls", {}).get("get")
        image_url = ""

        if prediction_url:
            for _ in range(20):
                poll = requests.get(prediction_url, headers={
                    "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}"
                }).json()
                status = poll.get("status")
                if status == "succeeded":
                    image_url = poll.get("output")[0] if poll.get("output") else ""
                    break
                elif status == "failed":
                    break
                time.sleep(1)

        if not image_url:
            image_url = "https://via.placeholder.com/512x512?text=Image+Not+Found"

        return jsonify({"image_url": image_url})
    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"})


# ------------------ YOUTUBE SEARCH -------------------
@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    data = request.json
    prompt = data.get("prompt")
    try:
        query = prompt.replace("YouTube", "").strip()
        search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&q={query}&key={os.getenv('YOUTUBE_API_KEY')}"
        res = requests.get(search_url).json()
        if res["items"]:
            vid = res["items"][0]
            video_id = vid["id"]["videoId"]
            title = vid["snippet"]["title"]
            return jsonify({"url": f"https://www.youtube.com/watch?v={video_id}", "title": title})
    except Exception as e:
        return jsonify({"error": f"YouTube search failed: {str(e)}"})

    return jsonify({"error": "No video found"})


# ------------------ TRACKING -------------------
@app.route("/track", methods=["POST"])
def track():
    data = request.json
    log = {
        "user_id": data.get("user_id"),
        "action": data.get("action"),
        "input": data.get("input"),
        "timestamp": data.get("timestamp")
    }
    try:
        with open("user_logs.json", "a") as f:
            f.write(json.dumps(log) + "\n")
    except Exception as e:
        print("Track log error:", e)
    return jsonify({"status": "ok"})


# ------------------ MAIN -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
