import random
import time
import json
from datetime import datetime

# Simple simulation of 100 AI humans
humans = []

cities = ["New York", "Delhi", "London", "Tokyo", "Paris", "Cairo", "Beijing"]
emotions = ["Happy", "Sad", "Neutral", "Angry", "Excited"]
jobs = ["Engineer", "Student", "Farmer", "Artist", "Doctor", "Unemployed"]
names = ["Aarav", "Liam", "Sofia", "Ravi", "Emma", "Mohammed", "Aiko", "Lucas"]

for _ in range(100):
    humans.append({
        "name": random.choice(names),
        "age": random.randint(1, 80),
        "emotion": random.choice(emotions),
        "job": random.choice(jobs),
        "money": random.randint(10, 10000),
        "city": random.choice(cities),
        "last_updated": datetime.utcnow().isoformat()
    })

# Auto evolve logic
def evolve():
    for person in humans:
        if random.random() < 0.2:
            person["emotion"] = random.choice(emotions)
        if random.random() < 0.1:
            person["money"] += random.randint(-50, 200)
        person["last_updated"] = datetime.utcnow().isoformat()

def run():
    while True:
        evolve()
        with open("src/engine/story_feed.txt", "w") as f:
            json.dump(humans, f)
        time.sleep(5)

if __name__ == "__main__":
    run()
