import json
import os
import random
import time

WORLD_FILE = os.path.join(os.getcwd(), "world_state.json")

emotions = ["Happy", "Sad", "Excited", "Angry", "Bored", "Curious", "Ambitious", "Tired"]
jobs = ["Engineer", "Artist", "Student", "Teacher", "Doctor", "Politician", "Developer", "Farmer"]
locations = ["USA", "India", "Germany", "Japan", "Brazil", "Canada", "France", "Australia"]

def update_world():
    if not os.path.exists(WORLD_FILE):
        return

    with open(WORLD_FILE, "r") as f:
        data = json.load(f)

    data["day"] += 1

    # Update humans
    for human in data.get("humans", []):
        human["age"] += 1 if random.random() < 0.1 else 0
        human["money"] += random.randint(-100, 300)
        human["emotion"] = random.choice(emotions)
        if random.random() < 0.2:
            human["job"] = random.choice(jobs)
        if random.random() < 0.1:
            human["location"] = random.choice(locations)

    # Change weather, economy, politics
    data["weather"] = random.choice(["Sunny", "Rainy", "Stormy", "Cloudy", "Snowy"])
    data["economy"]["globalGDP"] += random.randint(-10000, 20000)
    data["economy"]["marketTrend"] = random.choice(["Bullish", "Bearish", "Neutral"])
    data["politics"]["majorEvent"] = random.choice([
        "Climate summit ongoing",
        "Tech breakthrough announced",
        "New trade deal signed",
        "Elections approaching",
        "Peace talks resumed"
    ])

    with open(WORLD_FILE, "w") as f:
        json.dump(data, f, indent=2)

def run_forever():
    print("🌍 Live Earth engine started.")
    while True:
        update_world()
        time.sleep(10)  # Update every 10 seconds
