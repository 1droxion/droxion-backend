from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ✅ CORS: allow *.vercel.app and droxion.com
allowed_origin_regex = re.compile(
    r"^https:\/\/(.+\.)?droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$|^https:\/\/(www\.)?droxion\.com$|^https:\/\/droxion\.com$"
)
CORS(app, origins=allowed_origin_regex, supports_credentials=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ Code Generator
@app.route("/generate-code", methods=["POST"])
def generate_code():
    data = request.json
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-4",
                "messages": [
                    {
                        "role": "system",
                        "content": "You're a senior software engineer. Return clean, working code with step-by-step explanation. Use triple backtick Markdown format."
                    },
                    {"role": "user", "content": prompt}
                ]
            }
        )
        result = response.json()
        code = result["choices"][0]["message"]["content"]
        return jsonify({"code": code})
    except Exception as e:
        print("❌ Code Generation Error:", e)
        return jsonify({"error": "Failed to generate code."}), 500

# ✅ AI Chat
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": message}
                ]
            }
        )
        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        print("❌ Chat Error:", e)
        return jsonify({"error": "Failed to process chat."}), 500

# ✅ AI Image Generator
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024"
            }
        )
        result = response.json()
        image_url = result["data"][0]["url"]
        return jsonify({"image_url": image_url})
    except Exception as e:
        print("❌ Image Generation Error:", e)
        return jsonify({"error": "Failed to generate image."}), 500

# ✅ Test route
@app.route("/test")
def test():
    return jsonify({"message": "✅ Backend CORS OK, routes ready!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
