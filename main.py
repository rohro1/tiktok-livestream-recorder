import os
import logging
from flask import Flask, redirect, render_template, request, url_for
from threading import Thread
from time import sleep
from datetime import datetime
from src.utils.oauth_drive import get_drive_service
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_api import TikTokAPI
from src.core.tiktok_recorder import TikTokLiveRecorder
from src.utils.google_drive_uploader import GoogleDriveUploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

PORT = int(os.environ.get("PORT", 10000))
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))

app = Flask(__name__, template_folder="templates")

def read_usernames(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lstrip("@") for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("Usernames file not found: %s", path)
        return []

usernames = read_usernames(USERNAMES_FILE)
status_tracker = StatusTracker()
recorders = {}
uploaders = {}

def poll_loop():
    logger.info("Polling started (interval=%s)", POLL_INTERVAL)
    drive_service = get_drive_service("credentials.json", ["https://www.googleapis.com/auth/drive.file"])
    if not drive_service:
        logger.error("Google Drive service not initialized — authorize first")
        return
    for u in usernames:
        uploaders[u] = GoogleDriveUploader(drive_service, "TikTokRecordings")

    while True:
        for username in usernames:
            try:
                api = TikTokAPI(username)
                live_url = api.get_live_url()
                if live_url:
                    status_tracker.update_status(username, online=True)
                    if username not in recorders or not recorders[username].is_running():
                        recorder = TikTokLiveRecorder(api, uploaders[username])
                        if recorder.start_recording():
                            recorders[username] = recorder
                            status_tracker.update_status(username, recording=True)
                else:
                    status_tracker.update_status(username, online=False, recording=False)
                    rec = recorders.get(username)
                    if rec and rec.is_running():
                        rec.stop_recording()
            except Exception as e:
                logger.error("Error polling %s: %s", username, e)
        sleep(POLL_INTERVAL)

Thread(target=poll_loop, daemon=True).start()

@app.route("/")
def index():
    return redirect(url_for("status"))

@app.route("/status")
def status():
    rows = []
    for u in usernames:
        st = status_tracker.get_status(u)
        rows.append({
            "username": u,
            "profile_url": f"https://www.tiktok.com/@{u}",
            "last_online": st.get("last_online") or "N/A",
            "online": st.get("online", False),
            "recording": st.get("recording", False),
        })
    return render_template("status.html", rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
