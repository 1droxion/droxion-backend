from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# ✅ CORS configuration with all known Vercel and custom frontend domains
CORS(app, supports_credentials=True, origins=[
    "https://droxion-live-final-hdmgxr3r2-suchitbhai-g-patel.vercel.app",
    "https://droxion-live-final-2muybv5ap-suchitbhai-g-patel.vercel.app",
    "https://droxion-live-final-hajva0c5c-suchitbhai-g-patel.vercel.app",
    "https://droxion-live-final-7akpddwp-suchitbhai-g-patel.vercel.app",
    "https://www.droxion.com",
    "https://droxion.com"
])

@app.route("/")
def home():
    return "✅ Droxion API (code generator) is live."

# ✅ Test route for CORS check
@app.route("/test", methods=["GET", "OPTIONS"])
def test_cors():
    return jsonify({"message": "CORS is working correctly!"})

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
                        "content": "You're a senior software engineer. Return clean, working code with clear step-by-step explanation. Output code in Markdown triple-backtick format."
                    },
                    {"role": "user", "content": prompt}
                ]
            }
        )
        reply = response.json()["choices"][0]["message"]["content"]
        return jsonify({"code": reply})
    except Exception as e:
        print("❌ Code Generation Error:", e)
        return jsonify({"error": "Failed to generate code."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
