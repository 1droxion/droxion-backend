from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, datetime, pytz, requests

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- MEMORY ----------
def load_memory():
    try:
        with open("memory.json", "r") as f:
            return json.load(f)
    except:
        return {"name": "", "goals": [], "facts": []}

def save_memory(memory):
    with open("memory.json", "w") as f:
        json.dump(memory, f, indent=2)

# ---------- AGENT TASK RUNNER ----------
def run_agent_step(goal):
    prompt = f"What is the first step to achieve: {goal}? Just give the answer."
    res = client.chat.completions.create(
        model="gpt-4", messages=[{"role": "user", "content": prompt}]
    )
    step = res.choices[0].message.content.strip()
    return step

# ---------- AUTO-LEARN PHASE ----------
def learn_new_fact(fact):
    memory = load_memory()
    if fact not in memory["facts"]:
        memory["facts"].append(fact)
        save_memory(memory)

# ---------- CHAT ROUTE ----------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "").strip()
    voice_mode = data.get("voiceMode", False)
    memory = load_memory()
    reply = ""

    # --- SMART COMMANDS ---
    if prompt.lower().startswith("remember my name"):
        memory["name"] = prompt.replace("remember my name", "").strip()
        save_memory(memory)
        return jsonify({"reply": f"✅ Got it. I'll remember: *my name {memory['name']}*."})

    if prompt.lower() in ["my name", "what's my name?"]:
        return jsonify({"reply": f"Your name is {memory['name']}"})

    if prompt.lower().startswith("my goal is"):
        goal = prompt.replace("my goal is", "").strip()
        if goal not in memory["goals"]:
            memory["goals"].append(goal)
            save_memory(memory)
        return jsonify({"reply": f"✅ Goal saved: *{goal}*."})

    if prompt.lower() == "my goals":
        if memory["goals"]:
            return jsonify({"reply": "🎯 Your goals:\n- " + "\n- ".join(memory["goals"])})
        else:
            return jsonify({"reply": "You have no saved goals."})

    if prompt.lower().startswith("remember this:"):
        fact = prompt.replace("remember this:", "").strip()
        learn_new_fact(fact)
        return jsonify({"reply": f"🧠 Learned: *{fact}*"})

    if prompt.lower() == "my facts":
        if memory["facts"]:
            return jsonify({"reply": "📚 Your facts:\n- " + "\n- ".join(memory["facts"])})
        else:
            return jsonify({"reply": "No facts saved yet."})

    # --- AGENT MODE ---
    if prompt.lower() == "run agent":
        if not memory["goals"]:
            return jsonify({"reply": "⚠️ No goals set. Use `my goal is ...` first."})
        goal = memory["goals"][0]
        step = run_agent_step(goal)
        return jsonify({"reply": f"🤖 Auto-step for *{goal}*:\n`{step}`"})

    # --- GPT CHAT ---
    messages = [{"role": "system", "content": f"You are an advanced AGI assistant helping {memory['name']}."}]
    messages.append({"role": "user", "content": prompt})

    try:
        res = client.chat.completions.create(
            model="gpt-4",
            messages=messages
        )
        reply = res.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ Error from AI. Try again.\n\n{str(e)}"

    return jsonify({"reply": reply})

# ---------- IMAGE ANALYSIS (PHASE 7: MULTIMODAL VISION) ----------
@app.route("/analyze", methods=["POST"])
def analyze_image():
    data = request.json
    image_url = data.get("image")
    prompt = data.get("prompt", "What’s in this image?")
    try:
        res = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }],
            max_tokens=500
        )
        content = res.choices[0].message.content.strip()
        return jsonify({"reply": content})
    except Exception as e:
        return jsonify({"reply": f"❌ Vision error: {e}"}), 500

# ---------- IMAGE GENERATION ----------
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.json
    prompt = data.get("prompt", "")
    style = data.get("style", "Realistic")
    try:
        res = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {os.getenv('REPLIT_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "version": "YOUR_REPLIT_MODEL_VERSION",  # replace if needed
                "input": {
                    "prompt": f"{prompt}, {style}, 8k highly detailed",
                    "width": 512,
                    "height": 512
                }
            }
        )
        output = res.json()
        image_url = output.get("prediction", {}).get("output", [""])[-1]
        return jsonify({"image": image_url})
    except Exception as e:
        return jsonify({"error": str(e)})

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(debug=True)
