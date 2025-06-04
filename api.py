from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests
import re

# Load .env variables
load_dotenv()

app = Flask(__name__)

# ✅ CORS: Accept all Vercel subdomains and production domains using custom function
def custom_cors_origin(origin):
    allowed_domains = [
        "https://droxion.com",
        "https://www.droxion.com"
    ]
    if origin in allowed_domains:
        return True
    # Match any droxion-live-final-[hash].vercel.app
    return bool(re.match(r"^https:\/\/droxion-live-final.*\.vercel\.app$", origin))

CORS(app, origins=custom_cors_origin, supports_credentials=True)

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ Code generation endpoint
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
        result = response.json()
        code = result["choices"][0]["message"]["content"]
        return jsonify({"code": code})
    except Exception as e:
        print("❌ Code Generation Error:", e)
        return jsonify({"error": "Failed to generate code."}), 500

# ✅ CORS Test endpoint
@app.route("/test")
def test():
    return jsonify({"message": "CORS and backend working!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
