from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import logging
import time
import json
import subprocess

load_dotenv()
app = Flask(__name__)
CORS(app, origins=[
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
], supports_credentials=True)
logging.basicConfig(level=logging.INFO)

PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
os.makedirs(PUBLIC_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return jsonify({"reply": "❌ Missing OpenRouter API key"}), 500

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
            return jsonify({"reply": f"❌ Error: {result.get('message', 'Unknown error')}"}), 400

        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Exception: {str(e)}"}), 500

@app.route("/generate", methods=["POST"])
def generate_reel():
    try:
        config = request.get_json()
        config_mapped = {
            "topic": config.get("topic", ""),
            "language": config.get("language", "English"),
            "voice": config.get("voice", "onyx"),
            "voiceSpeed": config.get("voiceSpeed", 1.0),
            "clipCount": int(config.get("clipCount", 10)),
            "fontSize": 80,
            "subtitleColor": "white",
            "subtitlePosition": config.get("subtitlePosition", "bottom").lower(),
            "musicVolume": config.get("musicVolume", "medium"),
            "tone": config.get("style", "cinematic").lower(),
            "lengthSec": 25 if config.get("length") == "Short" else 35 if config.get("length") == "Medium" else 45,
            "filenameMode": "auto",
            "customFilename": "",
            "manualScript": "yes" if config.get("mode") == "Manual" else "no",
            "userScript": config.get("userScript", ""),
            "captionStyle": "sentence" if config.get("captions") == "Sentence" else "word" if config.get("captions") == "Word-by-Word" else "none",
            "branding": config.get("branding", "no").lower()
        }

        with open("config.json", "w") as f:
            json.dump(config_mapped, f)

        result = subprocess.run(["python", "auto_reel_final.py"], capture_output=True, text=True)
        print("▶️ Script Output:", result.stdout)
        print("❗ Script Error:", result.stderr)

        videos = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
        latest_video = max(videos, key=lambda x: os.path.getctime(os.path.join(PUBLIC_FOLDER, x)))
        return jsonify({"videoUrl": f"/videos/{latest_video}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"error": f"Exception: {str(e)}"}), 500

@app.route("/analyze-image", methods=["POST"])
def analyze_image():
    try:
        image = request.files.get("image")
        prompt = request.form.get("prompt", "").strip()

        if not image:
            return jsonify({"reply": "❌ No image uploaded."}), 400

        os.makedirs("temp", exist_ok=True)
        image_path = os.path.join("temp", "upload.jpg")
        image.save(image_path)

        gpt_prompt = f"The user uploaded an image. Prompt: '{prompt}'. Respond helpfully based on it."
        api_key = os.getenv("OPENROUTER_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are an AI image-aware assistant. Respond smartly to the user's image and prompt."},
                {"role": "user", "content": gpt_prompt}
            ]
        }
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        data = res.json()
        reply = data["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Image error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Missing prompt"}), 400

        yt_key = os.getenv("YOUTUBE_API_KEY")
        if not yt_key:
            return jsonify({"error": "Missing YouTube API key"}), 500

        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": prompt,
            "type": "video",
            "maxResults": 1,
            "key": yt_key
        }

        res = requests.get(url, params=params)
        data = res.json()

        if "items" not in data or not data["items"]:
            return jsonify({"error": "No video found"}), 404

        video = data["items"][0]
        video_id = video["id"]["videoId"]
        title = video["snippet"]["title"]

        return jsonify({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": title
        })
    except Exception as e:
        return jsonify({"error": f"Exception: {str(e)}"}), 500

@app.route("/youtube", methods=["POST"])
def youtube_alias():
    return search_youtube()

@app.route("/news", methods=["POST"])
def search_news():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"headlines": []})

        gnews_key = os.getenv("GNEWS_API_KEY")
        if not gnews_key:
            return jsonify({"headlines": []})

        url = f"https://gnews.io/api/v4/search?q={prompt}&lang=en&max=3&apikey={gnews_key}"
        res = requests.get(url)
        data = res.json()

        headlines = [a["title"] for a in data.get("articles", [])[:3]]
        return jsonify({"headlines": headlines})
    except Exception as e:
        return jsonify({"error": f"News error: {str(e)}"}), 500

@app.route("/videos/<filename>")
def serve_video(filename):
    return send_from_directory(PUBLIC_FOLDER, filename)

@app.route("/user-stats", methods=["GET"])
def user_stats():
    return jsonify({
        "coins": 999,
        "videosThisMonth": 0,
        "plan": {"videoLimit": 999}
    })

@app.route("/track", methods=["POST"])
def track():
    data = request.get_json()
    print("📊 Tracked session:", data)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
