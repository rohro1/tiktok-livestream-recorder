# main.py

import os
import threading
import time
from datetime import datetime
from flask import Flask, redirect, request, jsonify, url_for

# Google OAuth utils
from src.utils.oauth_drive import get_flow, save_credentials, get_drive_service

# Status tracker
from src.utils.status_tracker import StatusTracker

# TikTok recorder imports
from TikTokLiveRecorder.src.core.tiktok_recorder import TikTokRecorder

# -------------------------
# Flask App
# -------------------------
app = Flask(__name__)

# Instantiate status tracker
status_tracker = StatusTracker()

# -------------------------
# Google OAuth Routes
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
    save_credentials(flow.credentials)
    return "Google Drive authorized successfully!"

# -------------------------
# Status Page
# -------------------------
@app.route("/status")
def status():
    return jsonify(status_tracker.get_status())

# -------------------------
# TikTok Live Monitoring
# -------------------------
RECORDED_USERS = set()

def monitor_user(username):
    """Monitor TikTok username and record when live."""
    while True:
        try:
            is_live = TikTokRecorder.check_live(username)  # returns True/False
            if is_live and username not in RECORDED_USERS:
                status_tracker.set_online(username)
                RECORDED_USERS.add(username)

                # Start recording in background thread
                threading.Thread(target=record_livestream, args=(username,)).start()
            elif not is_live and username in RECORDED_USERS:
                status_tracker.set_offline(username)
                RECORDED_USERS.remove(username)
        except Exception as e:
            print(f"Error monitoring {username}: {e}")
        time.sleep(60)  # check every minute

def record_livestream(username):
    """Record livestream using TikTokRecorder."""
    try:
        recorder = TikTokRecorder(username, resolution="480p")
        date_folder = datetime.now().strftime("%m-%d-%Y")
        filename = f"{username}_{int(time.time())}.mp4"
        save_path = os.path.join("recordings", username, date_folder)
        os.makedirs(save_path, exist_ok=True)
        file_path = os.path.join(save_path, filename)

        recorder.record(file_path)  # blocks until stream ends

        # Upload to Google Drive
        drive_service = get_drive_service()
        TikTokRecorder.upload_to_drive(drive_service, username, file_path)

    except Exception as e:
        print(f"Error recording {username}: {e}")
    finally:
        status_tracker.set_offline(username)
        if username in RECORDED_USERS:
            RECORDED_USERS.remove(username)

# -------------------------
# Start monitoring all usernames from usernames.txt
# -------------------------
def start_monitoring():
    if not os.path.exists("usernames.txt"):
        print("usernames.txt not found")
        return
    with open("usernames.txt", "r") as f:
        usernames = [line.strip() for line in f if line.strip()]
    for username in usernames:
        threading.Thread(target=monitor_user, args=(username,), daemon=True).start()

# Start monitoring in background thread
threading.Thread(target=start_monitoring, daemon=True).start()

# -------------------------
# Root
# -------------------------
@app.route("/")
def index():
    return "TikTok Live Recorder is running!"

# -------------------------
# Run App
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
