import os
import threading
from flask import Flask, redirect, request, jsonify
from src.utils.oauth_drive import get_flow, save_credentials, get_drive_service, load_credentials
from src.utils.status_tracker import StatusTracker

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
# Livestream Monitoring Thread (simulation)
# -------------------------
def monitor_livestreams():
    import time

    while True:
        if os.path.exists("usernames.txt"):
            with open("usernames.txt", "r") as f:
                usernames = [line.strip() for line in f if line.strip()]
        else:
            usernames = []

        for user in usernames:
            status_tracker.update_user(
                username=user,
                online=True,  # simulate online
                recording_duration=5,
                last_online="2025-08-28 16:00:00",
                live_duration=300
            )
        time.sleep(10)

threading.Thread(target=monitor_livestreams, daemon=True).start()

# -------------------------
# Run Flask
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
