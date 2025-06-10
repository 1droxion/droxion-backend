import openai
import time
import os

# ✅ Load your OpenAI API key from environment
openai.api_key = os.getenv("OPENAI_API_KEY")

# ✅ Path to the story file
STORY_FILE = "engine/story_feed.txt"

# ✅ Get the last few days from the story file
def get_last_days(n=3):
    if not os.path.exists(STORY_FILE):
        return []
    with open(STORY_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines[-n:]

# ✅ Append a new day to the story
def write_day(entry):
    with open(STORY_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

# ✅ Generate the next day using GPT
def generate_next_day():
    history = get_last_days()
    prompt = "This is an AI-generated real-time evolving world. Here are the last few days of its history:\n\n"
    prompt += "\n".join(history)
    prompt += "\n\nWhat happens on the next day in 1 line? Reply in this format: [Day N]: 🌍 Text here"

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    next_line = response['choices'][0]['message']['content'].strip()
    return next_line

# ✅ Loop forever and evolve the world
def run_forever():
    while True:
        next_day = generate_next_day()
        print("🪐 Next:", next_day)
        write_day(next_day)
        time.sleep(60)  # 60 seconds = 1 real-time day
