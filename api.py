from flask import Flask, request, jsonify, render_template_string, make_response
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
from collections import Counter
from dateutil import parser
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

LOG_FILE = "user_logs.json"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/style-photo", methods=["POST"])
def style_photo():
    try:
        image_file = request.files.get("file")
        prompt = request.form.get("prompt", "").strip()
        style = request.form.get("style", "Pixar").strip()

        if not image_file:
            return jsonify({"error": "Missing image file"}), 400
        if not prompt:
            return jsonify({"error": "Missing prompt"}), 400

        imgbb_key = os.getenv("IMGBB_API_KEY")
        if not imgbb_key:
            return jsonify({"error": "Missing IMGBB_API_KEY"}), 500

        replicate_token = os.getenv("REPLICATE_API_TOKEN")
        if not replicate_token:
            return jsonify({"error": "Missing REPLICATE_API_TOKEN"}), 500

        upload = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": imgbb_key},
            files={"image": image_file}
        ).json()

        print("ImgBB Upload Response:", upload)
        if "data" not in upload or "url" not in upload["data"]:
            return jsonify({"error": "Failed to upload image to ImgBB"}), 500

        image_url = upload["data"]["url"]
        print("Uploaded Image URL:", image_url)

        headers = {
            "Authorization": f"Token {replicate_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "e1f9a3c078b2e1f1e503b964f88d23bb75e3c4f0f3318b9a5e9ee3b8c2a2239e",
            "input": {
                "image": image_url,
                "prompt": f"{prompt}, style {style}"
            }
        }

        res = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload).json()
        print("Replicate Response:", res)

        if "urls" not in res or "get" not in res["urls"]:
            return jsonify({"error": "Replicate API failed", "details": res}), 500

        poll_url = res["urls"]["get"]

        while True:
            poll = requests.get(poll_url, headers=headers).json()
            print("Polling:", poll)
            if poll["status"] == "succeeded":
                return jsonify({"image_url": poll["output"]})
            elif poll["status"] == "failed":
                return jsonify({"error": "Image generation failed", "details": poll}), 500
            time.sleep(1)

    except Exception as e:
        return jsonify({"error": f"Style Photo error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
