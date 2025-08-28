import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template, redirect, request, session, url_for
from src.utils.status_tracker import status_tracker
from src.utils.oauth_drive import get_flow, save_credentials, load_credentials, get_drive_service
from src.core.tiktok_recorder import TikTokRecorder

app = Flask(__name__)
app.secret_key = os.urandom(24)

USERNAMES_FILE = "usernames.txt"

# -----------------------
# Authorization Helpers
# -----------------------

def check_credentials():
    """
    Returns True if valid credentials exist, False otherwise.
    """
    creds = load_credentials()
    if creds and creds.valid:
        return True
    return False

# -----------------------
# OAuth Routes
# -----------------------

@app.route("/authorize")
def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    return render_template("authorize.html", auth_url=auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    save_credentials(credentials)
    return redirect("/status")

# -----------------------
# Status Routes
# -----------------------

@app.route("/")
def index():
    # Redirect to authorize if no valid credentials
    if not check_credentials():
        return redirect("/authorize")
    return redirect("/status")

@app.route("/status")
def status():
    if not check_credentials():
        return redirect("/authorize")

    # Retrieve current status
    status_data = status_tracker.get_status()
    # Render HTML template with live data
    return render_template("status.html", status=status_data)

# -----------------------
# Livestream Monitoring
# -----------------------

def monitor_livestreams():
    recorder = TikTokRecorder()
    usernames = []

    while True:
        # Reload usernames every 5 minutes
        if os.path.exists(USERNAMES_FILE):
            with open(USERNAMES_FILE, "r") as f:
                lines = f.readlines()
                new_usernames = [line.strip() for line in lines if line.strip()]
            if new_usernames != usernames:
                usernames = new_usernames
                status_tracker.init_users(usernames)

        # Check live status for each username
        for username in usernames:
            is_live = recorder.is_user_live(username)
            status_tracker.update_status(username, is_live)
            if is_live and not recorder.is_recording(username):
                # Start recording and uploading in a separate thread
                threading.Thread(target=recorder.record_and_upload, args=(username,), daemon=True).start()

        time.sleep(30)  # Poll every 30 seconds

# -----------------------
# Start Monitoring Thread
# -----------------------

threading.Thread(target=monitor_livestreams, daemon=True).start()

# -----------------------
# Run App
# -----------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
