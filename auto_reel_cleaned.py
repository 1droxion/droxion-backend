from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import subprocess
import os
import json
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Folder where videos are saved
PUBLIC_FOLDER = "C:/Users/16626/Downloads/droxion-ui-final/public"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    print("🔥 /generate hit with:", data)

    # Save config from frontend
    with open("config.json", "w") as f:
        json.dump(data, f)

    try:
        # Run the Python script that generates the video
        result = subprocess.run(
            ["python", "auto_reel_cleaned.py"],
            capture_output=True,
            text=True
        )
        print("📤 STDOUT:\n", result.stdout)
        print("❌ STDERR:\n", result.stderr)

        if result.returncode != 0:
            return jsonify({"status": "error", "message": result.stderr}), 500

        topic = data.get("topic", "Video")
        language = data.get("language", "English")
        now = datetime.now().strftime("%Y%m%d_%H%M")
        filename_mode = data.get("filenameMode", "auto")
        custom_filename = data.get("customFilename", "")

        if filename_mode == "manual" and custom_filename:
            final_filename = f"{custom_filename}.mp4"
        else:
            final_filename = f"{topic}_{language}_{now}.mp4"

        return jsonify({
            "status": "success",
            "message": "Video created.",
            "videoUrl": f"/{final_filename}"
        })
    except Exception as e:
        print("❌ SERVER ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/videos", methods=["GET"])
def list_videos():
    files = [f for f in os.listdir(PUBLIC_FOLDER) if f.endswith(".mp4")]
    data = []
    for file in files:
        parts = file.split("_")
        topic = parts[0] if len(parts) > 1 else "Unknown"
        modified = datetime.fromtimestamp(os.path.getmtime(os.path.join(PUBLIC_FOLDER, file)))
        data.append({
            "filename": file,
            "topic": topic,
            "date": modified.strftime("%Y-%m-%d %H:%M")
        })
    return jsonify(data)

@app.route("/delete/<filename>", methods=["DELETE"])
def delete_video(filename):
    try:
        path = os.path.join(PUBLIC_FOLDER, filename)
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"status": "deleted"})
        else:
            return jsonify({"status": "not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/videos/<filename>")
def serve_video(filename):
    return send_from_directory(PUBLIC_FOLDER, filename)

@app.route("/")
def home():
    return "Droxion API is running..."

@app.route("/chat", methods=["POST"])
def chat_with_ai():
    data = request.json
    user_message = data.get("message", "")
    print("📩 Message received from frontend:", user_message)

    headers = {
        "Authorization": f"Bearer {os.getenv('VITE_OPENAI_API_KEY')}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": user_message}
        ]
    }

    try:
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
        res.raise_for_status()
        print("✅ Response from OpenAI:", res.json())
        return jsonify(res.json())
    except requests.exceptions.RequestException as e:
        print("❌ ERROR from OpenAI:", e)
        if e.response:
            print("❌ ERROR BODY:", e.response.text)
        return jsonify({"error": "OpenAI call failed", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
