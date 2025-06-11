# genesis_engine.py
import json
import time
import random

STATE_FILE = "universe_state.json"

# Initial Big Bang state
def big_bang():
    return {
        "timestamp": time.time(),
        "age_seconds": 0,
        "era": "Big Bang",
        "temperature_K": 1e32,
        "volume": 1e-20,
        "matter": {
            "protons": 0,
            "electrons": 0,
            "neutrons": 0,
        },
        "space": {
            "dimensions": 3,
            "expanding": True,
            "rate": 1e10
        },
        "history": ["Big Bang initialized"]
    }

# Simulate expansion and cooling over time
def evolve_universe(state):
    state["age_seconds"] += 1e9  # simulate 1 billion seconds (~31 years)
    state["temperature_K"] *= 0.8
    state["volume"] *= 1.5

    if state["era"] == "Big Bang" and state["temperature_K"] < 1e27:
        state["era"] = "Quark Era"
        state["history"].append("Era changed to Quark Era")
        state["matter"]["protons"] = random.randint(100, 500)
        state["matter"]["electrons"] = random.randint(100, 500)

    elif state["era"] == "Quark Era" and state["temperature_K"] < 1e20:
        state["era"] = "Plasma Era"
        state["history"].append("Era changed to Plasma Era")

    elif state["era"] == "Plasma Era" and state["temperature_K"] < 1e10:
        state["era"] = "Stars Form"
        state["history"].append("First stars ignited")

    return state

# Load or initialize universe state
def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return big_bang()

# Save universe state
def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# Run forever (or in steps)
def run_forever():
    while True:
        state = load_state()
        state = evolve_universe(state)
        save_state(state)
        time.sleep(2)  # slow evolution for visualization
