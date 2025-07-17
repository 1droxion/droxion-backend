# ✅ api.py — AGI Phase 1–3 Backend

from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, time, datetime, requests
from openai import OpenAI

app = Flask(__name__)
CORS(app)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Load memory.json ---
MEMORY_FILE = "memory.json"
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump({"name": "Dhruv", "goals": [], "facts": []}, f)

def load_memory():
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --- Phase 1: Memory update ---
@app.route("/remember", methods=["POST"])
def remember():
    data = request.json
    key = data.get("key")
    value = data.get("value")
    mem = load_memory()

    if key == "name":
        mem["name"] = value
    elif key == "goal":
        mem["goals"].append(value)
    elif key == "fact":
        mem["facts"].append(value)

    save_memory(mem)
    return jsonify({"status": "saved"})

# --- Phase 2: Main Chat ---
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "")
    memory = load_memory()
    name = memory.get("name", "User")
    goals = memory.get("goals", [])
    facts = memory.get("facts", [])

    context = f"Your name is {name}.\nGoals: {goals}\nKnown facts: {facts}"

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)})

# --- Phase 3: Agent Execution (Step 1 only) ---
@app.route("/agent", methods=["POST"])
def agent():
    memory = load_memory()
    goals = memory.get("goals", [])
    if not goals:
        return jsonify({"task": "No goals set yet."})

    goal = goals[0]
    try:
        step_prompt = f"Break this goal into steps and perform the first one: {goal}"
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": step_prompt}]
        )
        step_result = response.choices[0].message.content

        with open("tasks.json", "a") as f:
            f.write(json.dumps({"goal": goal, "step1_result": step_result}) + "\n")

        return jsonify({"task": step_result})
    except Exception as e:
        return jsonify({"error": str(e)})

# --- Image generation (Replit) ---
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
                status = poll.get("status")
                if status == "succeeded":
                    image_url = poll.get("output")[0] if poll.get("output") else ""
                    break
                elif status == "failed":
                    break
                time.sleep(1)
        return jsonify({"image_url": image_url})
    except Exception as e:
        return jsonify({"error": str(e)})

# --- YouTube search ---
@app.route("/search-youtube", methods=["POST"])
def search_yt():
    data = request.json
    prompt = data.get("prompt")
    query = prompt.replace("YouTube", "").strip()
    try:
        yt_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&q={query}&key={os.getenv('YOUTUBE_API_KEY')}"
        res = requests.get(yt_url).json()
        if res["items"]:
            vid = res["items"][0]
            vid_id = vid["id"]["videoId"]
            title = vid["snippet"]["title"]
            return jsonify({"url": f"https://www.youtube.com/watch?v={vid_id}", "title": title})
    except Exception as e:
        return jsonify({"error": str(e)})
    return jsonify({"error": "No results found"})

# --- Run App ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
