from flask import Flask, request, jsonify, send_file
import subprocess
import os

app = Flask(__name__)

@app.route("/generate", methods=["POST"])
def generate_video():
    data = request.json
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    try:
        subprocess.run(["python", "generate.py", prompt], check=True)
        return send_file("output/video.mp4", as_attachment=True)
    except subprocess.CalledProcessError:
        return jsonify({"error": "Video generation failed"}), 500

if __name__ == "__main__":
    app.run(debug=True)
