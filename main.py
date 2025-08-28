import os
import threading
import time
from flask import Flask, redirect, request, url_for, render_template_string

from src.utils.oauth_drive import get_flow, save_credentials, get_drive_service
from src.utils.status_tracker import status_tracker
from src.core.tiktok_api import TikTokAPI
from src.core.recorder import Recorder
from src.utils.drive_manager import DriveManager

# Flask app
app = Flask(__name__)

# Globals
drive_service = None
drive_manager = None
monitor_thread = None
monitoring = False
USERNAME_FILE = "usernames.txt"


# ---------------------------
# Google OAuth Routes
# ---------------------------
@app.route("/authorize")
def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    global drive_service, drive_manager
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_credentials(creds)
    drive_service = get_drive_service()
    drive_manager = DriveManager(drive_service)
    return redirect(url_for("status"))


# ---------------------------
# Status Page
# ---------------------------
@app.route("/status")
def status():
    rows = []
    for username, data in status_tracker.get_all_status().items():
        rows.append(
            f"<tr><td>{username}</td>"
            f"<td>{'🟢 LIVE' if data['online'] else '⚪ Offline'}</td>"
            f"<td>{data['recording']}</td>"
            f"<td>{data['last_seen']}</td>"
            f"<td>{data['duration']}</td></tr>"
        )

    html = f"""
    <html>
    <head>
        <title>TikTok Livestream Recorder Status</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f5f5f5; }}
            h1 {{ text-align: center; }}
            table {{ border-collapse: collapse; margin: auto; width: 80%; background: white; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
            th {{ background: #eee; }}
        </style>
    </head>
    <body>
        <h1>TikTok Livestream Recorder Status</h1>
        <p style="text-align:center;">Google Drive {("✅ Authorized" if drive_service else "❌ Not Authorized")}</p>
        <table>
            <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Recording</th>
                <th>Last Seen</th>
                <th>Duration</th>
            </tr>
            {''.join(rows)}
        </table>
    </body>
    </html>
    """
    return render_template_string(html)


# ---------------------------
# Background TikTok Monitoring
# ---------------------------
def monitor_users():
    global drive_manager
    api = TikTokAPI()

    while True:
        if not drive_manager:
            time.sleep(10)
            continue

        if not os.path.exists(USERNAME_FILE):
            time.sleep(30)
            continue

        with open(USERNAME_FILE, "r") as f:
            usernames = [line.strip() for line in f if line.strip()]

        for username in usernames:
            try:
                live_info = api.is_live(username)
                if live_info["status"] == "online":
                    status_tracker.update_status(username, online=True, recording="Starting...")
                    recorder = Recorder(username, live_info["url"], drive_manager, status_tracker)
                    recorder.start_recording()
                else:
                    status_tracker.update_status(username, online=False)
            except Exception as e:
                print(f"Error checking {username}: {e}")

        time.sleep(300)  # check every 5 minutes


def start_monitor_thread():
    global monitor_thread, monitoring
    if not monitoring:
        monitor_thread = threading.Thread(target=monitor_users, daemon=True)
        monitor_thread.start()
        monitoring = True


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    # Start monitor thread
    start_monitor_thread()

    # Run Flask server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
