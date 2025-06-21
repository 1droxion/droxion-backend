from flask import Flask, request, jsonify, render_template_string, make_response
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, json, time
from datetime import datetime
from collections import Counter
from dateutil import parser
import pytz

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

LOG_FILE = "user_logs.json"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "droxion2025")

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response

def get_location_from_ip(ip):
    try:
        main_ip = ip.split(",")[0].strip()
        res = requests.get(f"http://ip-api.com/json/{main_ip}")
        data = res.json()
        if data["status"] == "success":
            return f"{data['city']}, {data['countryCode']}"
        return ""
    except:
        return ""

def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)

def log_user_action(user_id, action, input_text, ip):
    now = datetime.utcnow().isoformat() + "Z"
    location = get_location_from_ip(ip)
    new_entry = {
        "timestamp": now,
        "user_id": user_id,
        "action": action,
        "input": input_text,
        "ip": ip,
        "location": location
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        except:
            logs = []
    logs.append(new_entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def parse_logs(file_path, user_filter=None, days=7):
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    dau_set, wau_set, mau_set = set(), set(), set()
    hour_count = Counter()
    input_count = Counter()
    user_count = Counter()
    location_count = Counter()
    logs = []

    if os.path.exists(file_path):
        with open(file_path) as f:
            data = json.load(f)
        for entry in data:
            try:
                ts = parser.isoparse(entry["timestamp"]).replace(tzinfo=pytz.UTC)
                if (now - ts).days <= days:
                    uid = entry.get("user_id", "anonymous")
                    logs.append(entry)
                    dau_set.add(uid)
                    wau_set.add(uid)
                    mau_set.add(uid)
                    hour = ts.hour
                    hour_count[hour] += 1
                    input_count[entry.get("input", "").strip()] += 1
                    user_count[uid] += 1
                    location_count[entry.get("location", "")] += 1
            except:
                continue
    return {
        "dau": len(dau_set),
        "wau": len(wau_set),
        "mau": len(mau_set),
        "peak_hour": hour_count.most_common(1)[0][0] if hour_count else 0,
        "top_users": dict(user_count.most_common(3)),
        "top_inputs": dict(input_count.most_common(5)),
        "top_locations": dict(location_count.most_common(3)),
        "logs": logs[-100:]
    }

@app.route("/")
def home():
    return "✅ Droxion API is live."

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "")
    if token != ADMIN_TOKEN:
        return "❌ Unauthorized", 401
    user_filter = request.args.get("user")
    days = int(request.args.get("days", 7))
    stats = parse_logs(LOG_FILE, user_filter, days)

    html = """
    <style>
        body { background:#000; color:#fff; font-family:Arial; padding:20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #444; padding: 8px; text-align: left; }
        th { background-color: #222; }
        tr:nth-child(even) { background-color: #111; }
        h2, h4 { color: #0ff; }
    </style>
    <h2>📊 Droxion Dashboard</h2>
    <div>DAU: {{ stats['dau'] }} | WAU: {{ stats['wau'] }} | MAU: {{ stats['mau'] }}</div>
    <div>Peak Hour: {{ stats['peak_hour'] }}</div>
    <div>Top Users: {{ stats['top_users'] }}</div>
    <div>Top Inputs: {{ stats['top_inputs'] }}</div>
    <div>Top Locations: {{ stats['top_locations'] }}</div>
    <hr>
    <h4>User Activity Logs</h4>
    <table>
        <tr><th>Time</th><th>User</th><th>Action</th><th>Input</th><th>IP</th><th>Location</th></tr>
        {% for log in stats['logs'] %}
        <tr>
            <td>{{ log['timestamp'] }}</td>
            <td>{{ log['user_id'] }}</td>
            <td>{{ log['action'] }}</td>
            <td>{{ log['input'] }}</td>
            <td>{{ log['ip'] }}</td>
            <td>{{ log['location'] }}</td>
        </tr>
        {% endfor %}
    </table>
    """
    return render_template_string(html, stats=stats)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
