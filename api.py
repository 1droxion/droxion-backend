from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import time

load_dotenv()
app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

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
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are an assistant powered by Droxion."},
                {"role": "user", "content": prompt}
            ]
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

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
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 30,
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False
            }
        }

        create = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        prediction = create.json()
        get_url = prediction.get("urls", {}).get("get")

        while True:
            poll = requests.get(get_url, headers=headers).json()
            if poll.get("status") == "succeeded":
                return jsonify({"image_url": poll.get("output")})
            elif poll.get("status") == "failed":
                return jsonify({"error": "Image generation failed"}), 500
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
        path = os.path.join("temp", "upload.jpg")
        image.save(path)

        full_prompt = f"The user uploaded an image. Prompt: '{prompt}'. Describe or respond helpfully."
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You're an AI assistant that analyzes images and prompts together."},
                {"role": "user", "content": full_prompt}
            ]
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"❌ Error: {str(e)}"}), 500

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        prompt = request.json.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt required"}), 400

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
        return jsonify({
            "url": f"https://www.youtube.com/watch?v={video['id']['videoId']}",
            "title": video["snippet"]["title"]
        })
    except Exception as e:
        return jsonify({"error": f"Exception: {str(e)}"}), 500

@app.route("/news", methods=["POST"])
def search_news():
    try:
        prompt = request.json.get("prompt", "").strip()
        gnews_key = os.getenv("GNEWS_API_KEY")
        url = f"https://gnews.io/api/v4/search?q={prompt}&lang=en&max=3&apikey={gnews_key}"

        res = requests.get(url)
        articles = res.json().get("articles", [])[:3]
        headlines = [a["title"] for a in articles]
        return jsonify({"headlines": headlines})
    except Exception as e:
        return jsonify({"error": f"News error: {str(e)}"}), 500

@app.route("/classify", methods=["POST"])
def classify():
    try:
        prompt = request.json.get("prompt", "")
        api_key = os.getenv("OPENROUTER_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 🔥 Improved instruction
        messages = [
            {"role": "system", "content": (
                "Your task is to classify the user's prompt into one of four categories:\n"
                "- image: if the prompt asks to generate, create, draw, or show an image or picture\n"
                "- youtube: if the prompt asks to find, show, or watch a video or YouTube clip\n"
                "- news: if the prompt asks about news, headlines, or current events\n"
                "- chat: if it's just general conversation or doesn't fit above\n"
                "Reply with one word only: image, youtube, news, or chat."
            )},
            {"role": "user", "content": prompt}
        ]

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": messages
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        reply = res.json()["choices"][0]["message"]["content"].strip().lower()
        print(f"🧠 Prompt: {prompt} → Type: {reply}")
        return jsonify({"type": reply})
    except Exception as e:
        print(f"❌ Classify error: {str(e)}")
        return jsonify({"type": "chat", "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
