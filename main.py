import os
import threading
import time
from flask import Flask, redirect, url_for, render_template_string
from src.utils.oauth_drive import get_drive_service
from utils.status_tracker import status_tracker
from src.core.tiktok_api import TikTokAPI
from src.core.recorder import Recorder

app = Flask(__name__)

# --- Background TikTok monitor ---
def monitor_usernames():
    api = TikTokAPI()
    while True:
        if os.path.exists("usernames.txt"):
            with open("usernames.txt", "r") as f:
                usernames = [line.strip() for line in f if line.strip()]
        else:
            usernames = []

        for username in usernames:
            try:
                live_info = api.is_live(username)
                if live_info["is_live"]:
                    if not status_tracker.is_recording(username):
                        recorder = Recorder(username, live_info["url"])
                        t = threading.Thread(target=recorder.start_recording)
                        t.start()
                        status_tracker.set_online(username, True)
                else:
                    status_tracker.set_online(username, False)
            except Exception as e:
                print(f"Error checking {username}: {e}")

        time.sleep(300)  # check every 5 minutes


# --- Web routes ---
@app.route("/")
def index():
    return redirect(url_for("status"))

@app.route("/status")
def status():
    statuses = status_tracker.get_all_statuses()
    html = """
    <html>
    <head>
        <title>TikTok Livestream Recorder Status</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 30px; }
            h1 { color: #333; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f4f4f4; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            .online { color: green; font-weight: bold; }
            .offline { color: red; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>TikTok Livestream Recorder Status</h1>
        {% if statuses %}
        <table>
            <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Recording</th>
                <th>Current Duration</th>
                <th>Last Seen Online</th>
                <th>Last Live Duration</th>
            </tr>
            {% for user, info in statuses.items() %}
            <tr>
                <td>{{ user }}</td>
                <td class="{{ 'online' if info.online else 'offline' }}">
                    {{ "Online" if info.online else "Offline" }}
                </td>
                <td>{{ "Yes" if info.recording else "No" }}</td>
                <td>{{ info.duration if info.duration else "-" }}</td>
                <td>{{ info.last_seen if info.last_seen else "-" }}</td>
                <td>{{ info.last_duration if info.last_duration else "-" }}</td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p>No usernames are being tracked yet. Add them to <b>usernames.txt</b>.</p>
        {% endif %}
    </body>
    </html>
    """
    return render_template_string(html, statuses=statuses)


if __name__ == "__main__":
    # Start background monitoring in a thread
    t = threading.Thread(target=monitor_usernames, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
