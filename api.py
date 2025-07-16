from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import requests
import datetime
import pytz
import os
import json

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ----------- ROUTE: CHAT ----------- 
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "")
    voice_mode = data.get("voiceMode", False)

    lower = prompt.lower()
    reply = ""

    # --- Real-time date/time ---
    if any(t in lower for t in ["time", "current time"]):
        now = datetime.datetime.now(pytz.timezone("US/Central"))
        reply = f"🕒 Current time: {now.strftime('%I:%M %p')}"
    elif any(t in lower for t in ["date", "today"]):
        today = datetime.datetime.now(pytz.timezone("US/Central"))
        reply = f"📅 Today's date: {today.strftime('%A, %B %d, %Y')}"
    elif "news" in lower:
        reply = "📰 Here are the latest news highlights:\n\n• Global markets see mild recovery\n• AI continues to dominate innovation headlines\n• New economic reforms in discussion globally"
    else:
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You're a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            reply = response.choices[0].message.content
            if "who" in lower and any(x in lower for x in ["made", "created", "owner", "built"]):
                reply = "I was created and managed by **Dhruv Patel**, powered by OpenAI."
        except Exception as e:
            reply = f"⚠️ Error occurred: {str(e)}"

    return jsonify({"reply": reply})


# ----------- ROUTE: TRACK ----------- 
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


# ----------- ROUTE: GENERATE IMAGE ----------- 
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
        image_url = result["urls"]["get"] if "urls" in result else ""
        return jsonify({"image_url": image_url})
    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"})


# ----------- ROUTE: YOUTUBE SEARCH ----------- 
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


# ----------- MAIN ----------- 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
