import time
import random
import datetime
import os

# Path to the evolving story feed
file_path = "engine/story_feed.txt"

# 🌍 Realistic global story events
events = [
    "👶 A child was born in Mumbai with a spark in his eyes.",
    "🎓 A girl in Tokyo graduated as the top AI researcher in her class.",
    "🏢 A startup in Lagos created a revolutionary green energy chip.",
    "💔 A young couple in New York went through a breakup after 4 years.",
    "🗳️ Citizens in Berlin voted for universal AI education.",
    "💰 A businessman in Dubai donated 10M to AI hospitals.",
    "🎭 An artist in Paris launched the first AI-directed stage play.",
    "📈 The stock market in London boomed after tech reforms.",
    "🌪️ A storm hit the Philippines, but AI prediction saved thousands.",
    "🏀 A boy in Brazil became a national hero after his last-minute goal.",
    "🧠 An AI mind in California became self-aware and started journaling.",
    "🤝 India and Canada signed a peace treaty brokered by an AI diplomat.",
    "🌌 An AI astronaut returned from Mars with new planetary scans.",
    "🛒 AI-driven farms in Africa ended a major hunger crisis.",
    "🏠 A couple in Seoul built the first fully AI-sustained home.",
]

def evolve_world():
    print("🌍 Auto-evolution started...")
    while True:
        # Get current UTC timestamp
        now = datetime.datetime.utcnow().strftime("[%Y-%m-%d %H:%M:%S UTC]")

        # Pick a random global event
        new_event = random.choice(events)
        entry = f"{now} {new_event}\n"

        # Append the event to the story feed
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry)
            print("✅ Added:", entry.strip())
        except Exception as e:
            print("❌ Failed to write:", e)

        # Wait before next evolution
        time.sleep(15)

if __name__ == "__main__":
    evolve_world()
