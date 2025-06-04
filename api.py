from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# ✅ Correct CORS configuration with all frontend URLs
CORS(app, supports_credentials=True, origins=[
    "https://droxion.com",
    "https://www.droxion.com",
    "https://droxion-live-final.vercel.app",
    "https://droxion-live-final-6sgs09n9c-suchitbhai-g-patel.vercel.app",
])

@app.route("/")
def home():
    return "✅ Droxion API is live."

# ✅ Code Generator Endpoint
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

# ✅ Example fallback endpoint (optional)
@app.route("/test")
def test():
    return jsonify({"message": "CORS and backend working!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
