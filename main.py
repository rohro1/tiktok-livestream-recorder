import os
import threading
import time
from flask import Flask, redirect, url_for, render_template_string

# Corrected imports
from src.utils.oauth_drive import get_drive_service
from src.utils.status_tracker import status_tracker
from src.core.tiktok_api import TikTokAPI
from src.core.recorder import Recorder

app = Flask(__name__)

drive_service = None
recorders = {}
tiktok_api = TikTokAPI()

@app.route("/")
def index():
    if drive_service:
        return redirect(url_for("status"))
    return '<a href="/authorize">Authorize Google Drive</a>'

@app.route("/authorize")
def authorize():
    from src.utils.oauth_drive import authorize_url
    return redirect(authorize_url())

@app.route("/oauth2callback")
def oauth2callback():
    global drive_service
    from src.utils.oauth_drive import oauth2callback_handler
    drive_service = oauth2callback_handler()
    return "Google Drive authorization completed! <a href='/status'>Go to Status</a>"

@app.route("/status")
def status():
    template = """
    <h1>TikTok Livestream Recorder Status</h1>
    {% if not drive_service %}
        <p>Google Drive not authorized. <a href='/authorize'>Authorize here</a></p>
    {% else %}
        <p>Google Drive authorization completed!</p>
        <table border="1" cellpadding="5">
            <tr><th>Username</th><th>Status</th><th>Recording</th><th>Last Online</th><th>Last Duration</th></tr>
            {% for user, data in status_data.items() %}
            <tr>
                <td>{{ user }}</td>
                <td>{{ "ONLINE" if data.online else "OFFLINE" }}</td>
                <td>{{ data.recording }}</td>
                <td>{{ data.last_online }}</td>
                <td>{{ data.last_duration }}</td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}
    """
    return render_template_string(template, drive_service=drive_service, status_data=status_tracker.status)

def monitor_users():
    while True:
        if drive_service:
            with open("usernames.txt") as f:
                usernames = [line.strip() for line in f if line.strip()]

            for username in usernames:
                if username not in recorders:
                    recorders[username] = Recorder(username, drive_service)

                is_live = tiktok_api.is_user_live(username)
                recorders[username].update_status(is_live)

        time.sleep(300)  # every 5 minutes

if __name__ == "__main__":
    threading.Thread(target=monitor_users, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))