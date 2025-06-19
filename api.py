from flask import Flask, request, jsonify, make_response
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
import os
import requests
import base64
import time
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser
from collections import Counter

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "https://www.droxion.com",
    "https://droxion.com",
    "https://droxion.vercel.app",
    "http://localhost:5173"
]}}, supports_credentials=True)

LOG_FILE = "user_logs.json"

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token")
    if token != "droxion2025":
        return "❌ Unauthorized", 403

    if not os.path.exists(LOG_FILE):
        return "<h3>No activity logs found.</h3>"

    with open(LOG_FILE) as f:
        logs = json.load(f)

    now = datetime.now(timezone.utc)
    days = int(request.args.get("days", 30))
    filter_user = request.args.get("user")

    filtered_logs = []
    users_1d, users_7d, users_30d = set(), set(), set()
    hour_usage = []
    user_counts = Counter()
    locations = Counter()
    queries = Counter()

    for log in logs:
        t = parser.isoparse(log["timestamp"])
        uid = log["user_id"]
        if now - t <= timedelta(days=1): users_1d.add(uid)
        if now - t <= timedelta(days=7): users_7d.add(uid)
        if now - t <= timedelta(days=30): users_30d.add(uid)

        if now - t <= timedelta(days=days):
            if not filter_user or uid == filter_user:
                filtered_logs.append(log)
                hour_usage.append(t.hour)
                user_counts[uid] += 1
                if log.get("location"): locations[log["location"]] += 1
                if log.get("input"): queries[log["input"]] += 1

    peak_hour = Counter(hour_usage).most_common(1)
    top_locations = locations.most_common(3)
    top_queries = queries.most_common(5)

    html = f"""
    <html><head><title>Droxion Dashboard</title>
    <style>
    body {{ background: #111; color: #eee; font-family: sans-serif; padding: 20px; }}
    .card {{ background: #222; padding: 10px; margin: 8px 0; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th, td {{ border: 1px solid #444; padding: 6px; font-size: 13px; }}
    th {{ background-color: #222; }}
    tr:nth-child(even) {{ background-color: #1a1a1a; }}
    </style></head><body>
    <h2>📊 Droxion Dashboard</h2>
    <div class='card'>DAU: {len(users_1d)} | WAU: {len(users_7d)} | MAU: {len(users_30d)}</div>
    <div class='card'>Peak usage hour: {peak_hour[0][0]}:00</div>
    <div class='card'>Top Users: {dict(user_counts.most_common(3))}</div>
    <div class='card'>Top Locations: {dict(top_locations)}</div>
    <div class='card'>Top Inputs: {dict(top_queries)}</div>
    <div class='card'>Filter: ?token=droxion2025&days=7&user=yourid</div>

    <h3>User Activity Logs</h3>
    <table>
    <tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
    """

    for log in reversed(filtered_logs[-100:]):
        html += f"<tr><td>{log['timestamp']}</td><td>{log['user_id']}</td><td>{log['action']}</td><td>{log.get('input','')}</td><td>{log.get('ip','')}</td><td>{log.get('location','')}</td></tr>"

    html += "</table></body></html>"
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
