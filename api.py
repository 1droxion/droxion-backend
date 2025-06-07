from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re

# Load .env environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)

# ✅ Allow CORS from all known Droxion frontends
allowed_origin_regex = re.compile(
    r"^https:\/\/(www\.)?droxion\.com$|"
    r"^https:\/\/droxion(-live-final)?(-[a-z0-9]+)?\.vercel\.app$"
)
CORS(app, supports_credentials=True, origins=allowed_origin_regex)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ AI IMAGE GENERATOR (Replicate)
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        print("🖼️ Image prompt:", prompt)

        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",  # Stable SDXL
                "input": {
                    "prompt": prompt,
                    "width": 1024,
                    "height": 1024,
                    "num_inference_steps": 30,
                    "refine": "expert_ensemble_refiner",
                    "apply_watermark": False
                }
            }
        )
        result = response.json()
        print("🖼️ Replicate result:", result)

        image_url = result["output"][0] if "output" in result else None
        if not image_url:
            return jsonify({"error": "Failed to generate image."}), 500

        return jsonify({"url": image_url})

    except Exception as e:
        print("❌ Image Generation Error:", e)
        return jsonify({"error": "Image generation failed."}), 500

# ✅ AI CHAT (OpenRouter)
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    try:
        data = request.json
        print("📩 Incoming chat data:", data)

        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required."}), 400

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return jsonify({"error": "OpenRouter API key missing."}), 500

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openrouter/openchat",
            "messages": [
                {"role": "system", "content": "You are an assistant powered by Droxion."},
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )

        print("🤖 OpenRouter status:", response.status_code)
        result = response.json()
        print("✅ OpenRouter result:", result)

        reply = result["choices"][0]["message"]["content"] if "choices" in result else "⚠️ No reply."
        return jsonify({"reply": reply})

    except Exception as e:
        print("❌ Chat Error:", e)
        return jsonify({"error": "Chat generation failed."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
