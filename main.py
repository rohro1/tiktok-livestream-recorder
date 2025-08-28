# main.py
import os
import threading
from flask import Flask, redirect, request, jsonify
from utils.oauth_drive import get_flow, save_credentials, get_drive_service, load_credentials
from utils.status_tracker import StatusTracker

app = Flask(__name__)

status_tracker = StatusTracker()

# -------------------------
# OAuth Routes
# -------------------------
@app.route("/authorize")
def authorize():
    flow = get_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    return redirect(authorization_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_credentials(creds)
    return "Authorization successful! You can close this page."

# -------------------------
# Status Route
# -------------------------
@app.route("/status")
def status():
    return jsonify(status_tracker.get_status())

# -------------------------
# Dummy Livestream Monitoring Thread
# -------------------------
def monitor_livestreams():
    import time
    usernames = ["example_user1", "example_user2"]  # Replace with usernames.txt logic if needed
    while True:
        for user in usernames:
            # Simulate online/offline and recording duration
            status_tracker.update_user(
                username=user,
                online=True,
                recording_duration=5,  # seconds, just example
                last_online="2025-08-28 16:00:00",
                live_duration=300
            )
        time.sleep(10)  # check every 10 seconds

threading.Thread(target=monitor_livestreams, daemon=True).start()

# -------------------------
# Run App
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
