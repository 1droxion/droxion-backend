from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import time
import base64

load_dotenv()
app = Flask(__name__)
CORS(app, origins=["*"], supports_credentials=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/chat", methods=["POST"])
def chat():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"reply": "❗ Prompt is required."}), 400

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are an AI assistant created by Dhruv Patel and powered by Droxion™."},
                {"role": "user", "content": prompt}
            ]
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Exception: {str(e)}"}), 500

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        prompt = request.json.get("prompt", "").strip()
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
                "width": 768,
                "height": 768,
                "num_inference_steps": 30,
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False
            }
        }

        create = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        prediction = create.json()
        get_url = prediction.get("urls", {}).get("get")

        while True:
            poll = requests.get(get_url, headers=headers)
            poll_result = poll.json()
            if poll_result.get("status") == "succeeded":
                return jsonify({"image_url": poll_result.get("output")})
            elif poll_result.get("status") == "failed":
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

        # Read and base64 encode
        image_bytes = image.read()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }

        messages = [
            {"role": "system", "content": "You are an AI image analyzer assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]

        payload = {
            "model": "gpt-4-vision-preview",
            "messages": messages,
            "max_tokens": 500
        }

        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Image error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Missing prompt"}), 400

        key = os.getenv("YOUTUBE_API_KEY")
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": prompt,
            "type": "video",
            "maxResults": 1,
            "key": key
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

@app.route("/news", methods=["POST"])
def search_news():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"headlines": []})

        gnews_key = os.getenv("GNEWS_API_KEY")
        url = f"https://gnews.io/api/v4/search?q={prompt}&lang=en&max=3&apikey={gnews_key}"

        res = requests.get(url)
        articles = res.json().get("articles", [])[:3]
        headlines = [a["title"] for a in articles]
        return jsonify({"headlines": headlines})
    except Exception as e:
        return jsonify({"error": f"News error: {str(e)}"}), 500

@app.route("/talk-avatar", methods=["POST"])
def talk_avatar():
    try:
        image = request.files.get("image")
        script = request.form.get("prompt", "")
        if not image or not script:
            return jsonify({"error": "Image and script required"}), 400

        image_data = base64.b64encode(image.read()).decode("utf-8")
        headers = {
            "Authorization": f"Basic {os.getenv('DID_API_KEY')}",
            "Content-Type": "application/json"
        }

        payload = {
            "source_url": f"data:image/jpeg;base64,{image_data}",
            "script": {
                "type": "text",
                "input": script,
                "provider": {"type": "microsoft", "voice_id": "en-US-JennyNeural"}
            }
        }

        res = requests.post("https://api.d-id.com/talks", headers=headers, json=payload)
        data = res.json()
        video_url = data.get("result_url", "")
        return jsonify({"video_url": video_url})
    except Exception as e:
        return jsonify({"error": f"Avatar error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
