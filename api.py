from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import requests
import datetime
import pytz
import os
import json
import time

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ----------------- AGI MEMORY -------------------
def load_memory():
    try:
        with open("memory.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_memory(memory):
    with open("memory.json", "w") as f:
        json.dump(memory, f, indent=2)

# --------------- ROUTE: /chat -------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"reply": "⚠️ Empty prompt."})

    voice_mode = data.get("voiceMode", False)
    lower = prompt.lower()
    reply = ""

    # --- Smart Responses ---
    if lower.startswith("stock:"):
        stock = lower.replace("stock:", "").strip().upper()
        reply = f"📈 <b>{stock} Live Stock:</b><br><iframe src='https://www.google.com/finance/quote/{stock}:NASDAQ' width='100%' height='200'></iframe>"
    elif lower.startswith("crypto:"):
        coin = lower.replace("crypto:", "").strip().upper()
        reply = f"💰 <b>{coin} Live Crypto:</b><br><iframe src='https://www.google.com/search?q={coin}+price' width='100%' height='150'></iframe>"
    elif "time in" in lower:
        city = lower.split("time in")[-1].strip().title()
        now = datetime.datetime.now(pytz.timezone("US/Central"))
        reply = f"🕒 Current time in {city}: {now.strftime('%I:%M %p')}"
    elif "weather" in lower:
        city = lower.split("weather")[-1].strip().title()
        reply = f"⛅ Weather in {city}:<br><iframe src='https://www.google.com/search?q=weather+in+{city}' width='100%' height='150'></iframe>"
    elif "news" in lower:
        reply = "📰 Latest Headlines:<br>• AI breakthroughs in 2025<br>• Markets show global volatility<br>• Climate targets spark debates"
    elif "date" in lower:
        today = datetime.datetime.now(pytz.timezone("US/Central"))
        reply = f"📅 Today is {today.strftime('%A, %B %d, %Y')}"
    else:
        try:
            memory = load_memory()
            history = [
                {"role": "system", "content": f"User memory: {json.dumps(memory)}"},
                {"role": "user", "content": prompt}
            ]
            res = client.chat.completions.create(
                model="gpt-4",
                messages=history
            )
            reply = res.choices[0].message.content
        except Exception as e:
            reply = f"⚠️ AI Error: {str(e)}"

    return jsonify({"reply": reply})


# ------------- AGI MEMORY WRITE -----------------
@app.route("/remember", methods=["POST"])
def remember():
    data = request.json
    key = data.get("key")
    value = data.get("value")
    memory = load_memory()
    memory[key] = value
    save_memory(memory)
    return jsonify({"message": f"✅ Got it. I’ll remember: {key} = {value}"})


# --------- AGI PHASE 3: AGENT EXECUTOR ----------
@app.route("/agent", methods=["POST"])
def agent():
    data = request.json
    step = data.get("step")
    goal = data.get("goal")

    if not step or not goal:
        return jsonify({"error": "Missing step or goal."})

    try:
        res = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Execute: {step} for goal: {goal}"},
                {"role": "user", "content": step}
            ]
        )
        output = res.choices[0].message.content
        log = {
            "goal": goal,
            "step": step,
            "result": output,
            "timestamp": datetime.datetime.now().isoformat()
        }
        with open("tasks.json", "a") as f:
            f.write(json.dumps(log) + "\n")
        return jsonify({"result": output})
    except Exception as e:
        return jsonify({"error": f"⚠️ Agent failed: {str(e)}"})


# -------------- PHASE 4: /learn ------------------
@app.route("/learn", methods=["POST"])
def learn():
    data = request.json
    feedback = data.get("feedback", "").strip()
    if not feedback:
        return jsonify({"error": "Feedback is empty"})

    memory = load_memory()
    try:
        res = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Current memory: {json.dumps(memory)}"},
                {"role": "user", "content": f"Update memory based on this: {feedback}"}
            ]
        )
        new_memory = res.choices[0].message.content
        try:
            parsed = json.loads(new_memory)
            save_memory(parsed)
            return jsonify({"message": "✅ Learned and updated memory."})
        except:
            return jsonify({"reply": new_memory})
    except Exception as e:
        return jsonify({"error": f"Learning failed: {str(e)}"})


# ---------- IMAGE GENERATION (REPLIT) ------------
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt")
    try:
        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "db21e45a-df6d-4845-90c5-6e1f01b16f3f",
                "input": {"prompt": prompt}
            }
        )
        result = response.json()
        prediction_url = result.get("urls", {}).get("get")
        image_url = ""
        if prediction_url:
            for _ in range(20):
                poll = requests.get(prediction_url, headers={
                    "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}"
                }).json()
                if poll.get("status") == "succeeded":
                    image_url = poll.get("output")[0]
                    break
                elif poll.get("status") == "failed":
                    break
                time.sleep(1)
        return jsonify({"image_url": image_url})
    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"})


# --------------- YOUTUBE SEARCH ------------------
@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    data = request.json
    prompt = data.get("prompt")
    try:
        query = prompt.replace("YouTube", "").strip()
        search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&q={query}&key={os.getenv('YOUTUBE_API_KEY')}"
        res = requests.get(search_url).json()
        if res["items"]:
            vid = res["items"][0]
            video_id = vid["id"]["videoId"]
            title = vid["snippet"]["title"]
            return jsonify({"url": f"https://www.youtube.com/watch?v={video_id}", "title": title})
    except Exception as e:
        return jsonify({"error": f"YouTube search failed: {str(e)}"})
    return jsonify({"error": "No video found"})


# ----------------- TRACKING ----------------------
@app.route("/track", methods=["POST"])
def track():
    data = request.json
    log = {
        "user_id": data.get("user_id"),
        "action": data.get("action"),
        "input": data.get("input"),
        "timestamp": data.get("timestamp")
    }
    try:
        with open("user_logs.json", "a") as f:
            f.write(json.dumps(log) + "\n")
    except Exception as e:
        print("Track log error:", e)
    return jsonify({"status": "ok"})


# -------------- MAIN -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
