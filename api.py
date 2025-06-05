from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re
import time

# Load env vars (if local)
load_dotenv()

app = Flask(__name__)

# ✅ CORS for Droxion
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ CHAT — do not change
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
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

# ✅ CODE GEN — do not change
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
                    {"role": "system", "content": "You're a senior software engineer. Return clean, working code with explanation in triple-backticks."},
                    {"role": "user", "content": prompt}
                ]
            }
        )
        result = response.json()
        code = result["choices"][0]["message"]["content"]
        return jsonify({"code": code})
    except Exception as e:
        print("❌ Code Error:", e)
        return jsonify({"error": "Failed to generate code."}), 500

# ✅ IMAGE GEN — updated to Replicate SDXL only
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
                "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
                "input": {
                    "width": 1024,
                    "height": 1024,
                    "prompt": final_prompt,
                    "refine": "expert_ensemble_refiner",
                    "apply_watermark": False,
                    "num_inference_steps": 25
                }
            }
        )
        result = response.json()

        if "error" in result:
            return jsonify({"error": result["error"]}), 500

        prediction_url = result.get("urls", {}).get("get")
        if not prediction_url:
            return jsonify({"error": "Missing prediction URL"}), 500

        # Poll for status
        status = result.get("status", "")
        while status not in ["succeeded", "failed"]:
            time.sleep(2)
            poll = requests.get(prediction_url, headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}"
            }).json()
            status = poll.get("status", "")
            if status == "succeeded":
                return jsonify({"url": poll["output"][0]})
            elif status == "failed":
                return jsonify({"error": "Image generation failed."}), 500

        return jsonify({"error": "Image timed out."}), 500

    except Exception as e:
        print("❌ Image Error:", e)
        return jsonify({"error": "Image generation crashed."}), 500

# ✅ Test route
@app.route("/test")
def test():
    return jsonify({"message": "✅ CORS OK"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
