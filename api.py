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
CORS(app, supports_credentials=True, origins="*")

# === Public Folder ===
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
        print(f"🎨 Style request: {style}")
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
            "autoGenerates": 6,  # Simulated count — replace with DB later
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
def chat_with_ai():
    data = request.json
    user_message = data.get("message", "").strip().lower()

    if not user_message:
        return jsonify({"reply": "Please ask something like 'how to create a reel' or 'what is Droxion'."})

    if "droxion" in user_message or "what is this" in user_message:
        reply = "🤖 Droxion is an AI-powered content creation system. It helps you generate voice-over videos, edit automatically, add styles, and post reels — all using AI automation. Perfect for creators and marketers."
    elif "video" in user_message:
        reply = "🎥 To generate a video, go to the Generator tab, enter your topic, pick a voice and style, then click Generate!"
    elif "voice" in user_message:
        reply = "🗣️ Voice is added automatically using AI. You can choose between voices or use Hindi/English text."
    elif "help" in user_message or "how" in user_message:
        reply = "🆘 Need help? You can ask how to generate reels, upload styles, or manage credits. I'm here to assist!"
    else:
        reply = f"🤖 You said: \"{user_message}\" — I’ll support more smart responses soon. Keep exploring Droxion!"

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
