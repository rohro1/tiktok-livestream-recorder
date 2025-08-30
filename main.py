import os
import logging
from flask import Flask, redirect, render_template, request, url_for, abort, jsonify
from threading import Thread
from time import sleep
from datetime import datetime
import json

from src.utils.oauth_drive import (
    create_auth_url,
    fetch_and_store_credentials,
    get_drive_service,
    TOKEN_PATH,
)
from src.utils.status_tracker import StatusTracker
from src.utils.folder_manager import make_user_folders
from src.utils.google_drive_uploader import GoogleDriveUploader
from src.core.tiktok_recorder import TikTokLiveRecorder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

PORT = int(os.environ.get("PORT", 10000))
OAUTH_CREDENTIALS_FILE = os.environ.get("OAUTH_CREDENTIALS_FILE", "credentials.json")
OAUTH_REDIRECT = os.environ.get("OAUTH_REDIRECT", None)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "recordings")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "12"))

app = Flask(__name__, template_folder="templates")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# === global state ===
status_tracker = StatusTracker()
recorders = {}
uploaders = {}
usernames = []

def read_usernames(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("No usernames.txt found")
        return []

def recording_output_path(username):
    os.makedirs(os.path.join(RECORDINGS_DIR, username), exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(RECORDINGS_DIR, username, f"{username}_{ts}.mp4")

def is_drive_authorized():
    return os.path.exists(TOKEN_PATH)

def poll_loop():
    logger.info("Starting poll loop (interval=%s)", POLL_INTERVAL)
    global uploaders
    make_user_folders(usernames, RECORDINGS_DIR)

    drive_service = None
    if is_drive_authorized():
        drive_service = get_drive_service(OAUTH_CREDENTIALS_FILE, SCOPES)
        if drive_service:
            for u in usernames:
                uploaders[u] = GoogleDriveUploader(
                    drive_service, drive_folder_root="TikTokRecordings"
                )
            logger.info("Drive uploader initialized for users")

    while True:
        for username in usernames:
            try:
                # === check if live using yt-dlp ===
                import subprocess
                cmd = ["yt-dlp", f"https://www.tiktok.com/@{username}/live", "--dump-json"]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout.strip())
                    stream_url = data.get("url") or data.get("manifest_url")
                    is_live = bool(stream_url)
                else:
                    is_live = False

                if is_live:
                    status_tracker.update_status(username, online=True)
                    if username not in recorders or not recorders[username].is_running():
                        out_path = recording_output_path(username)
                        recorder = TikTokLiveRecorder(username, resolution="480p")
                        if recorder.start_recording(out_path):
                            recorders[username] = recorder
                            status_tracker.set_recording_file(username, out_path)
                            status_tracker.update_status(username, recording=True)
                else:
                    status_tracker.update_status(username, online=False)
                    rec = recorders.get(username)
                    if rec and rec.is_running():
                        rec.stop_recording()
                        out_file = status_tracker.get_recording_file(username)
                        if out_file and os.path.exists(out_file) and username in uploaders:
                            try:
                                uploaders[username].upload_file(out_file, remote_subfolder=username)
                            except Exception as e:
                                logger.exception("Upload failed: %s", e)
                        status_tracker.set_recording_file(username, None)
                        status_tracker.update_status(username, recording=False)

            except Exception as e:
                logger.exception("Error polling %s: %s", username, e)

        sleep(POLL_INTERVAL)

@app.route("/")
def index():
    return redirect(url_for("status"))

@app.route("/authorize")
def authorize():
    if is_drive_authorized():
        return redirect(url_for("status"))
    redirect_uri = OAUTH_REDIRECT or (request.url_root.rstrip("/") + "/oauth2callback")
    auth_url = create_auth_url(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri)
    return render_template("authorize.html", auth_url=auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    if is_drive_authorized():
        return redirect(url_for("status"))
    redirect_uri = OAUTH_REDIRECT or (request.url_root.rstrip("/") + "/oauth2callback")
    creds = fetch_and_store_credentials(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri, request.url)
    if creds:
        logger.info("OAuth success — saved token.json")
    else:
        logger.warning("OAuth failed")
    return redirect(url_for("status"))

@app.route("/status")
def status():
    rows = []
    for username in usernames:
        st = status_tracker.get_status(username)
        rows.append({
            "username": username,
            "last_online": st.get("last_online") or "N/A",
            "live_duration": st.get("live_duration", 0),
            "online": st.get("online", False),
            "recording": st.get("recording", False),
            "recording_file": st.get("recording_file", None),
        })
    return render_template("status.html", rows=rows, is_authorized=is_drive_authorized())

if __name__ == "__main__":
    usernames = read_usernames(USERNAMES_FILE)
    Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
