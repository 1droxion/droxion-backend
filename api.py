from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import subprocess
import os
import json
from datetime import datetime
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.after_request
def allow_all_frontends(response):
    origin = request.headers.get("Origin", "")
    if "vercel.app" in origin or "droxion.com" in origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    return response

# === Public folder setup ===
PUBLIC_FOLDER = os.path.join(os.getcwd(), "public")
if not os.path.exists(PUBLIC_FOLDER):
    os.makedirs(PUBLIC_FOLDER)

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/upload-image", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "No image received"}), 400
    image = request.files["image"]
    input_path = os.path.join(PUBLIC_FOLDER, "style_input.png")
    image.save(input_path)
    return jsonify({"status": "success", "image_url": "/style_input.png"})

@app.route("/upload-avatar", methods=["POST"])
def upload_avatar():
    if "avatar" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["avatar"]
    path = os.path.join(PUBLIC_FOLDER, "avatar.png")
    file.save(path)
    return jsonify({"url": f"/avatar.png"})

@app.route("/ai-style", methods=["POST"])
def ai_style():
    try:
        data = request.json
        style = data.get("style", "Ghibli")
        subprocess.run(["python", "src/ai_style_transform.py", style], check=True)
        return jsonify({"status": "success", "styledUrl": "/styled_output.png"})
    except Exception as e:
        print("❌ AI Style Error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    print("🔥 /generate hit with:", data)
    with open("config.json", "w") as f:
        json.dump(data, f)
    try:
        env = os.environ.copy()
        subprocess.run(["python", "auto_reel_final.py"], check=True, env=env)
        topic = data.get("topic", "Video")
        language = data.get("language", "English")
        now = datetime.now().strftime("%Y%m%d_%H%M")
        filename_mode = data.get("filenameMode", "auto")
        custom_filename = data.get("customFilename", "")
        final_filename = f"{custom_filename}.mp4" if filename_mode == "manual" and custom_filename else f"{topic}_{language}_{now}.mp4"
        save_path = os.path.join(PUBLIC_FOLDER, final_filename)
        if os.path.exists(save_path):
            return jsonify({
                "status": "success",
                "message": "Video created.",
                "videoUrl": f"/{final_filename}",
                "filename": final_filename,
                "topic": topic,
                "date": now
            })
        else:
            return jsonify({"status": "error", "message": "Video not found after generation."}), 500
    except subprocess.CalledProcessError as e:
        print("❌ Generation Error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/videos", methods=["GET"])
def list_videos():
    files = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
    result = []
    for file in files:
        filepath = os.path.join(PUBLIC_FOLDER, file)
        created_time = os.path.getctime(filepath)
        formatted_time = datetime.fromtimestamp(created_time).strftime("%Y-%m-%d %H:%M:%S")
        result.append({"filename": file, "date": formatted_time})
    result.sort(key=lambda x: x['date'], reverse=True)
    return jsonify(result)

@app.route("/delete/<filename>", methods=["DELETE"])
def delete_video(filename):
    try:
        path = os.path.join(PUBLIC_FOLDER, filename)
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"status": "deleted"})
        return jsonify({"status": "not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/<filename>")
def serve_file(filename):
    return send_from_directory(PUBLIC_FOLDER, filename)

@app.route("/user-stats", methods=["GET"])
def user_stats():
    try:
        stats = {
            "credits": 18,
            "videosThisMonth": len([f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]),
            "imagesThisMonth": len([f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".png") and "styled" in f]),
            "autoGenerates": 6,
            "plan": {
                "name": "Starter",
                "videoLimit": 5,
                "imageLimit": 20,
                "autoLimit": 10
            }
        }
        return jsonify(stats)
    except Exception as e:
        print("❌ Stats Error:", e)
        return jsonify({"error": "Could not fetch stats"}), 500

@app.route("/chat", methods=["POST"])
def chat_with_openrouter():
    data = request.json
    user_message = data.get("message", "")
    if not user_message:
        return jsonify({"reply": "❌ Empty message. Please ask something."}), 400
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
                    {"role": "system", "content": "You are a helpful assistant inside the Droxion platform. Reply simply and clearly."},
                    {"role": "user", "content": user_message}
                ]
            }
        )
        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        print("❌ OpenRouter Chat Error:", e)
        return jsonify({"reply": "⚠️ Error contacting AI. Please try again."}), 500

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
                    {"role": "system", "content": "You're a senior software engineer. Return clean, working code with clear step-by-step explanation. Output code in Markdown triple-backtick format."},
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
    app.run(host="0.0.0.0", port=5000, debug=True)
