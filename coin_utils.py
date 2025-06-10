import os
import json

USER_DB = os.path.join(os.getcwd(), "users.json")

def get_user(user_id="demo_user"):
    with open(USER_DB, "r") as f:
        users = json.load(f)
    return users.get(user_id, {"coins": 0, "plan": "None"})

def update_user_coins(user_id="demo_user", coins=0):
    with open(USER_DB, "r") as f:
        users = json.load(f)

    if user_id not in users:
        users[user_id] = {"coins": 0, "plan": "None"}

    users[user_id]["coins"] = coins

    with open(USER_DB, "w") as f:
        json.dump(users, f)
