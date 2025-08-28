import os
import threading
import datetime
import time
from flask import Flask, redirect, request, session, url_for, render_template_string

from src.utils.oauth_drive import get_flow, set_credentials, get_drive_service
from src.utils.status_tracker import StatusTracker

# --- Flask setup ---
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecret")

status_tracker = StatusTracker()

# --- Google Drive OAuth Routes ---
@app.route("/authorize")
def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)

    if not flow.credentials:
        return "Authorization failed.", 400

    # Save credentials
    set_credentials(flow.credentials)

    session["credentials"] = True
    return redirect(url_for("status"))


# --- Status Page ---
@app.route("/status")
def status():
    creds_ok = "Yes" if "credentials" in session else "No"

    # build HTML for each tracked user
    statuses = status_tracker.get_all_statuses()
    user_rows = ""
    for username, info in statuses.items():
        user_rows += f"""
        <tr>
            <td>{username}</td>
            <td>{"🟢 Online" if info['online'] else "⚪ Offline"}</td>
            <td>{info['recording_duration']}</td>
            <td>{info['last_online']}</td>
            <td>{info['last_duration']}</td>
        </tr>
        """

    html = f"""
    <h1>TikTok Livestream Recorder Status</h1>
    <p>Google Drive Authorized: {creds_ok}</p>
    <table border="1" cellpadding="6">
        <tr>
            <th>Username</th>
            <th>Status</th>
            <th>Recording Duration</th>
            <th>Last Online</th>
            <th>Last Duration</th>
        </tr>
        {user_rows}
    </table>
    """
    return render_template_string(html)


# --- Background Monitor (dummy for now) ---
def background_monitor():
    """
    Simulates livestream detection and updates the tracker.
    Replace this with real TikTok API detection + recorder.
    """
    usernames_file = "usernames.txt"

    while True:
        if os.path.exists(usernames_file):
            with open(usernames_file, "r") as f:
                usernames = [line.strip() for line in f if line.strip()]
        else:
            usernames = []

        for u in usernames:
            # fake online toggle
            now = datetime.datetime.now().strftime("%H:%M:%S")
            status_tracker.update_status(
                username=u,
                online=True,
                recording_duration=f"{now} running",
                last_online=now,
                last_duration="--"
            )

        time.sleep(30)  # check every 30 sec


if __name__ == "__main__":
    # start background monitor
    t = threading.Thread(target=background_monitor, daemon=True)
    t.start()

    # run web server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
