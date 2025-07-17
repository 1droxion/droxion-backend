from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import requests, os, json, time

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------- MEMORY MANAGEMENT ---------
def load_memory():
    try:
        with open("memory.json") as f:
            return json.load(f)
    except:
        return {"name": "", "goals": [], "facts": []}

def save_memory(data):
    with open("memory.json", "w") as f:
        json.dump(data, f, indent=2)

def save_task(step, output):
    try:
        with open("tasks.json", "r") as f:
            tasks = json.load(f)
    except:
        tasks = []
    tasks.append({"step": step, "output": output})
    with open("tasks.json", "w") as f:
        json.dump(tasks, f, indent=2)

# --------- PHASE 1–4: SMART CHAT ---------
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt", "").strip()
        memory = load_memory()
        lower = prompt.lower()

        if "remember my name" in lower:
            memory["name"] = prompt.split()[-1].strip().capitalize()
            save_memory(memory)
            return jsonify({"reply": f"✅ Got it. I'll remember: *my name {memory['name']}*."})

        if lower in ["my name", "what's my name?"]:
            return jsonify({"reply": f"Your name is {memory['name']}."})

        if lower.startswith("goal:") or lower.startswith("my goal is"):
            goal = prompt.split("goal:",1)[-1].strip() if "goal:" in lower else prompt.split("my goal is",1)[-1].strip()
            memory["goals"].append(goal)
            save_memory(memory)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You are Droxion AGI. Help user achieve goals using memory: {memory}"},
                    {"role": "user", "content": f"My current goal: {goal}. What is step 1?"}
                ]
            )
            step1 = response.choices[0].message.content.strip()
            save_task(step1, "(waiting to run)")
            return jsonify({"reply": f"🧠 Step 1 for *{goal}*:\n{step1}"})

        if "list my goals" in lower:
            goals = memory.get("goals", [])
            if not goals:
                return jsonify({"reply": "❌ No goals saved yet."})
            reply = "🎯 **Your Goals:**\n" + "\n".join([f"{i+1}. {g}" for i, g in enumerate(goals)])
            return jsonify({"reply": reply})

        # fallback: general AI chat
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"⚠️ Error: {str(e)}"})

# --------- PHASE 1: MEMORY MANUAL ADD ---------
@app.route("/remember", methods=["POST"])
def remember():
    data = request.json
    input_text = data.get("input", "")
    memory = load_memory()
    memory['facts'].append(input_text)
    save_memory(memory)
    return jsonify({"status": "✅ Saved to memory."})

# --------- PHASE 3: AGENT AUTO EXECUTE ---------
@app.route("/agent", methods=["POST"])
def agent():
    data = request.json
    goal = data.get("goal")
    step = data.get("step")
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "user", "content": f"Run this task:\nGoal: {goal}\nStep: {step}"}
            ]
        )
        result = response.choices[0].message.content
        save_task(step, result)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"result": f"⚠️ Error: {str(e)}"})

# --------- PHASE 7: IMAGE ANALYSIS (VISION) ---------
@app.route("/analyze-image", methods=["POST"])
def analyze_image():
    image_url = request.json.get("url")
    try:
        res = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": "Analyze this image."},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]}
            ],
            max_tokens=500
        )
        return jsonify({"analysis": res.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)})

# --------- PHASE 8: SEARCH YOUTUBE ---------
@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    query = request.json.get("prompt")
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        search_id = os.getenv("SEARCH_ENGINE_ID")
        url = f"https://www.googleapis.com/customsearch/v1?q={query}+site:youtube.com&key={api_key}&cx={search_id}"
        res = requests.get(url).json()
        item = res["items"][0]
        return jsonify({"title": item["title"], "url": item["link"]})
    except Exception as e:
        return jsonify({"error": f"❌ YouTube error: {str(e)}"})

# --------- PHASE 9: IMAGE GENERATION ---------
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
        for _ in range(20):
            poll = requests.get(prediction_url, headers={
                "Authorization": f"Token {os.getenv('REPLICATE_API_TOKEN')}"
            }).json()
            if poll.get("status") == "succeeded":
                return jsonify({"image_url": poll["output"][0]})
            time.sleep(1)
    except Exception as e:
        return jsonify({"error": f"Image generation failed: {str(e)}"})

# --------- LAUNCH ---------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
