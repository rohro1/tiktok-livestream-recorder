# main.py

import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, redirect, request

from utils.status_tracker import status_tracker
from utils.oauth_drive import get_flow, save_credentials, get_drive_service

# Import TikTokRecorder from local src/core folder
from src.core.tiktok_recorder import TikTokRecorder  # make sure this file exists

app = Flask(__name__)

# -------------------------
# Global variables
# -------------------------
USERNAME_FILE = "usernames.txt"
CHECK_INTERVAL = 300  # 5 minutes
recorders = {}  # {username: TikTokRecorder instance}


# -------------------------
# Google OAuth endpoints
# -------------------------
@app.route("/authorize")
def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_credentials(creds)
    return "Google Drive authorization complete!"


# -------------------------
# Status endpoint
# -------------------------
@app.route("/status")
def status():
    return jsonify(status_tracker.get_status())


# -------------------------
# Monitor usernames and start recording
# -------------------------
def monitor_usernames():
    while True:
        if os.path.exists(USERNAME_FILE):
            with open(USERNAME_FILE, "r") as f:
                usernames = [line.strip() for line in f if line.strip()]
            for username in usernames:
                if username not in recorders:
                    recorder = TikTokRecorder(username, status_tracker)
                    t = threading.Thread(target=recorder.run, daemon=True)
                    t.start()
                    recorders[username] = recorder
        time.sleep(CHECK_INTERVAL)


# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    # Start monitoring thread
    threading.Thread(target=monitor_usernames, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
