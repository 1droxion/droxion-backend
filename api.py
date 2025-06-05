from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ✅ CORS configuration
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ AI Chat Endpoint
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        # Identity override
        if re.search(r"who (made|created) you|your creator", message, re.IGNORECASE):
            return jsonify({"reply": "I was created by Dhruv Patel and powered by Droxion™. Owned by Dhruv Patel."})

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

# ✅ Code Generation Endpoint
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
                        "content": "You're a senior software engineer. Return clean, working code with step-by-step explanation. Output code in Markdown triple-backtick format."
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

# ✅ Image Generation (Advanced Replicate)
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt", "").strip()
    style = data.get("style", "realistic")

    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    enhancers = {
        "realistic": "ultra detailed, 4k, photorealistic, cinematic lighting, masterpiece",
        "anime": "anime style, colorful, crisp line art, detailed background",
        "ghibli": "ghibli style, whimsical, vibrant colors, cinematic, storybook",
        "pixel": "pixel art, 16-bit, retro game scene, blocky design",
        "3d": "Pixar style, soft lighting, cinematic 3D render, smooth detail",
    }

    final_prompt = f"{prompt}, {enhancers.get(style, enhancers['realistic'])}"

    try:
        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "db21e45e...",  # Replace with your Replicate model version
                "input": {
                    "prompt": final_prompt,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 1
                }
            }
        )
        result = response.json()
        image_url = result["prediction"]["output"][0]
        return jsonify({"url": image_url})

    except Exception as e:
        print("❌ AI Image Error:", e)
        return jsonify({"error": "Image generation failed."}), 500

@app.route("/test")
def test():
    return jsonify({"message": "✅ CORS is working."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
