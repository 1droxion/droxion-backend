from flask import Flask, request, jsonify, make_response, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time, traceback, sys
from datetime import datetime

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

ROUTER_KEY = os.getenv("ROUTER_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

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

        headers = {
            "Authorization": f"Bearer {ROUTER_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are Droxion AI Assistant."},
                {"role": "user", "content": prompt}
            ]
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_data = res.json()

        if "choices" not in response_data:
            return jsonify({"reply": f"❌ OpenAI Error: {response_data.get('error', {}).get('message', 'No response')}"}), 500

        reply = response_data["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except Exception as e:
        print("[Chat Error]", traceback.format_exc(), file=sys.stdout, flush=True)
        return jsonify({"reply": f"❌ Server Error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "")
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": prompt,
            "type": "video",
            "maxResults": 1,
            "key": YOUTUBE_API_KEY
        }
        res = requests.get(url, params=params).json()
        item = res["items"][0]
        video_id = item["id"]["videoId"]
        return jsonify({
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })
    except Exception as e:
        return jsonify({"error": f"YouTube error: {str(e)}"}), 500

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            "input": {
                "prompt": prompt,
                "width": 768,
                "height": 768
            }
        }

        r = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload).json()
        poll_url = r["urls"]["get"]

        while True:
            poll = requests.get(poll_url, headers=headers).json()
            if poll["status"] == "succeeded":
                return jsonify({"image_url": poll["output"]})
            elif poll["status"] == "failed":
                return jsonify({"error": "Image generation failed"}), 500
            time.sleep(1)

    except Exception as e:
        return jsonify({"error": f"Image error: {str(e)}"}), 500

@app.route("/style-photo", methods=["POST"])
def style_photo():
    try:
        image_file = request.files.get("file")
        prompt = request.form.get("prompt", "").strip()
        style = request.form.get("style", "Pixar").strip()

        if not image_file:
            return jsonify({"error": "Missing image file"}), 400
        if not prompt:
            return jsonify({"error": "Missing prompt"}), 400

        upload = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": image_file}
        ).json()

        print("[IMGBB Upload Response]", upload, file=sys.stdout, flush=True)

        if "data" not in upload or "url" not in upload["data"]:
            return jsonify({"error": "Image upload failed", "details": upload}), 500

        image_url = upload["data"]["url"]

        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "8ef2637dcd8b451b7f6f12e423d5a551d13a6501503681c60236e2c1825f3d10",
            "input": {
                "image": image_url,
                "prompt": f"{prompt}, {style}"
            }
        }

        response = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload).json()
        print("[Replicate API Response]", response, file=sys.stdout, flush=True)

        if "urls" not in response or "get" not in response["urls"]:
            return jsonify({"error": "Replicate API failed", "details": response}), 500

        poll_url = response["urls"]["get"]

        while True:
            poll = requests.get(poll_url, headers=headers).json()
            print("[Polling Result]", poll, file=sys.stdout, flush=True)
            if poll["status"] == "succeeded":
                return jsonify({"image_url": poll["output"][0]})
            elif poll["status"] == "failed":
                return jsonify({"error": "Image generation failed", "details": poll}), 500
            time.sleep(1)

    except Exception as e:
        print("[Style Photo Error]", traceback.format_exc(), file=sys.stdout, flush=True)
        return jsonify({"error": f"Server exception: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
