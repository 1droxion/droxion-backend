from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import requests, os, json, time, datetime, pytz

app = Flask(__name__)
CORS(app)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load memory
def load_memory():
    try:
        with open("memory.json") as f:
            return json.load(f)
    except:
        return {"name": "", "goals": [], "facts": []}

# Save memory
def save_memory(data):
    with open("memory.json", "w") as f:
        json.dump(data, f, indent=2)

# Save task output
def save_task(step, output):
    try:
        with open("tasks.json", "r") as f:
            tasks = json.load(f)
    except:
        tasks = []
    tasks.append({"step": step, "output": output})
    with open("tasks.json", "w") as f:
        json.dump(tasks, f, indent=2)

# Phase 1–4: Smart response with memory
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("prompt", "").strip()
    memory = load_memory()
    lower = prompt.lower()
    reply = ""

    if "remember my name" in lower:
        memory["name"] = prompt.split()[-1].strip().capitalize()
        save_memory(memory)
        return jsonify({"reply": f"✅ Got it. I'll remember: *my name {memory['name'].lower()}*."})

    if lower in ["my name", "what's my name?"]:
        return jsonify({"reply": f"Your name is {memory['name']}.")

    if lower.startswith("goal:"):
        goal = prompt.split("goal:",1)[-1].strip()
        memory["goals"].append(goal)
        save_memory(memory)
        return jsonify({"reply": f"✅ Saved your goal: *{goal}*. I’ll help you achieve it."})

    if "list my goals" in lower:
        goals = memory.get("goals", [])
        if not goals:
            return jsonify({"reply": "❌ No goals saved yet."})
        reply = "🎯 **Your Goals:**\n" + "\n".join([f"{i+1}. {g}" for i, g in enumerate(goals)])
        return jsonify({"reply": reply})

    # Phase 2–3: Plan step 1
    if memory['goals']:
        current_goal = memory['goals'][-1]
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You are Droxion AGI. Memory: {memory}. Help the user reach their goals."},
                    {"role": "user", "content": f"My current goal: {current_goal}. What is step 1?"}
                ]
            )
            step1 = response.choices[0].message.content.strip()
            save_task(step1, "(waiting to run)")
            return jsonify({"reply": f"🧠 Step 1 for *{current_goal}*:\n{step1}"})
        except Exception as e:
            return jsonify({"reply": f"⚠️ Error: {str(e)}"})

    # Fallback: normal chat
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"⚠️ Error from AI. Try again."
    return jsonify({"reply": reply})

# Phase 4: Auto-Learning
@app.route("/learn", methods=["POST"])
def learn():
    data = request.json
    new_fact = data.get("fact")
    memory = load_memory()
    if new_fact and new_fact not in memory['facts']:
        memory['facts'].append(new_fact)
        save_memory(memory)
        return jsonify({"status": "✅ Learned new fact."})
    return jsonify({"status": "⚠️ Fact already known or empty."})

# Phase 5: Reflect on tasks
@app.route("/reflect", methods=["GET"])
def reflect():
    try:
        with open("tasks.json") as f:
            tasks = json.load(f)
        insights = ""
        for task in tasks:
            insights += f"- Step: {task['step']}\n  ➤ Output: {task['output']}\n"
        return jsonify({"reflection": f"🔍 Reflection:\n{insights}"})
    except:
        return jsonify({"reflection": "❌ No task data available."})

# Phase 6: Self-improve (simplified)
@app.route("/improve", methods=["POST"])
def improve():
    memory = load_memory()
    improved_facts = list(set(memory['facts']))
    memory['facts'] = improved_facts
    save_memory(memory)
    return jsonify({"status": "✅ Facts deduplicated & improved."})

# Phase 7: Multimodal — Vision
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

# Phase 8: Web action
@app.route("/search-web", methods=["POST"])
def search_web():
    q = request.json.get("query")
    try:
        url = f"https://www.googleapis.com/customsearch/v1?q={q}&key={os.getenv('GOOGLE_API_KEY')}&cx={os.getenv('SEARCH_ENGINE_ID')}"
        res = requests.get(url).json()
        top = res['items'][0] if res.get('items') else {}
        return jsonify({"result": top.get("title", "No title"), "link": top.get("link", "No link")})
    except:
        return jsonify({"result": "❌ Web search failed."})

# Phase 9: Tool use (auto image gen)
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

# Phase 10: Autonomy — Self-run mode
@app.route("/auto", methods=["POST"])
def auto():
    memory = load_memory()
    if not memory["goals"]:
        return jsonify({"status": "❌ No goal to run."})
    goal = memory["goals"][-1]
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": f"Break this down and auto-run: {goal}"}]
        )
        plan = response.choices[0].message.content
        save_task(goal, plan)
        return jsonify({"status": "✅ AGI has started working on your goal.", "plan": plan})
    except Exception as e:
        return jsonify({"status": f"❌ Error: {str(e)}"})

# Server start
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
