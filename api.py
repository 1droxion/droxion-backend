from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import requests

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.after_request
def allow_all_frontends(response):
    origin = request.headers.get("Origin")
    allowed = [
        "vercel.app",
        "droxion.com",
        "droxion-live-final-ncl9al81n-suchitbhai-g-patel.vercel.app"  # ✅ YOUR frontend domain
    ]
    if origin and any(domain in origin for domain in allowed):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    if request.method == "OPTIONS":
        response.status_code = 200
    return response

@app.route("/")
def home():
    return "✅ Droxion API (code generator) is live."

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
