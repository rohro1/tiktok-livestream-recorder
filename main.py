import os
import threading
import time
from flask import Flask, jsonify, render_template_string
from utils.status_tracker import StatusTracker
from recorder import TikTokRecorder
from tiktok_api import TikTokAPI

app = Flask(__name__)

status_tracker = StatusTracker()
api = TikTokAPI()
recorders = {}

# HTML template for /status page
STATUS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TikTok Recorder Status</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 30px; background: #f9f9f9; }
        h1 { color: #333; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
        th { background: #eee; }
        tr:nth-child(even) { background: #f2f2f2; }
    </style>
</head>
<body>
    <h1>📡 TikTok Livestream Recorder - Status</h1>
    <table>
        <tr>
            <th>Username</th>
            <th>Status</th>
            <th>Recording Duration</th>
            <th>Last Online</th>
            <th>Last Live Duration</th>
        </tr>
        {% for user, info in statuses.items() %}
        <tr>
            <td>{{ user }}</td>
            <td>{{ info["status"] }}</td>
            <td>{{ info["recording_duration"] }}</td>
            <td>{{ info["last_online"] }}</td>
            <td>{{ info["last_live_duration"] }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

@app.route("/")
def home():
    return "<h2>✅ TikTok Recorder is running!</h2><p>Visit <a href='/status'>/status</a> to view livestream recording status.</p>"

@app.route("/status")
def status_page():
    statuses = status_tracker.get_all_statuses()
    return render_template_string(STATUS_TEMPLATE, statuses=statuses)

def monitor_user(username):
    """Monitor a single TikTok username for livestreams"""
    while True:
        try:
            is_live, stream_url = api.is_user_live(username)
            if is_live:
                if username not in recorders or not recorders[username].is_recording:
                    status_tracker.update_status(username, "ONLINE")
                    recorder = TikTokRecorder(username, stream_url, status_tracker)
                    recorders[username] = recorder
                    threading.Thread(target=recorder.start_recording, daemon=True).start()
            else:
                status_tracker.update_status(username, "OFFLINE")
        except Exception as e:
            print(f"Error monitoring {username}: {e}")
        time.sleep(60)  # check every 1 min

def load_usernames():
    """Load usernames from usernames.txt"""
    if not os.path.exists("usernames.txt"):
        return []
    with open("usernames.txt", "r") as f:
        return [line.strip() for line in f if line.strip()]

def start_monitoring():
    """Start monitoring all usernames"""
    usernames = load_usernames()
    for username in usernames:
        if username not in recorders:
            threading.Thread(target=monitor_user, args=(username,), daemon=True).start()

if __name__ == "__main__":
    threading.Thread(target=start_monitoring, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
