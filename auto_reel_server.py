from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os

app = Flask(__name__)
CORS(app)  # ✅ Enables CORS globally

@app.route("/")
def home():
    return jsonify({"message": "Droxion backend running!"})

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        print("📥 Received from frontend:", data)

        # ✅ Replace with your own script logic
        subprocess.run(["python", "auto_reel_final.py"], check=True)

        output_path = "videos/final_video.mp4"
        if os.path.exists(output_path):
            return jsonify({"videoUrl": f"http://localhost:5000/{output_path}"})
        else:
            return jsonify({"message": "Video not found!"}), 404

    except subprocess.CalledProcessError as e:
        print("❌ Script crashed:", e)
        return jsonify({"message": "Generation failed!"}), 500
    except Exception as e:
        print("❌ Unknown error:", str(e))
        return jsonify({"message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
