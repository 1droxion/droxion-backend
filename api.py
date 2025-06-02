from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import subprocess
import os
import json
from datetime import datetime
import requests  # ✅ Needed for OpenRouter

# Load .env if available
load_dotenv()

app = Flask(__name__)

# ✅ CORS support
CORS(app, supports_credentials=True)

@app.after_request
def allow_vercel_preview(response):
    origin = request.headers.get("Origin")
    if origin and "vercel.app" in origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    if request.method == "OPTIONS":
        response.status_code = 200
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

# ✅ OpenRouter-based Chat
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
