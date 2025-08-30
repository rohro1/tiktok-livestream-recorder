import os
import logging
from flask import Flask, redirect, render_template, request, url_for
from threading import Thread
from time import sleep
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service, TOKEN_PATH
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_api import TikTokAPI
from src.core.tiktok_recorder import TikTokLiveRecorder
from src.utils.folder_manager import make_user_folders
from src.utils.google_drive_uploader import GoogleDriveUploader

PORT = int(os.environ.get("PORT", 10000))
OAUTH_CREDENTIALS_FILE = os.environ.get("OAUTH_CREDENTIALS_FILE", "credentials.json")
OAUTH_REDIRECT = os.environ.get("OAUTH_REDIRECT", None)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "recordings")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "12"))

app = Flask(__name__, template_folder="templates")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

def read_usernames(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if u:
                    out.append(u)
    except FileNotFoundError:
        logger.warning("usernames file not found: %s", path)
    return out

usernames = read_usernames(USERNAMES_FILE)

status_tracker = StatusTracker()
recorders = {}
uploaders = {}

def recording_output_path(username):
    os.makedirs(os.path.join(RECORDINGS_DIR, username), exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(RECORDINGS_DIR, username, f"{username}_{ts}.mp4")

def poll_loop():
    logger.info("Starting poll loop (interval=%s)", POLL_INTERVAL)
    make_user_folders(usernames, RECORDINGS_DIR)
    drive_service = get_drive_service()
    if drive_service:
        for u in usernames:
            uploaders[u] = GoogleDriveUploader(drive_service, drive_folder_root="TikTokRecordings")
    
    while True:
        for username in usernames:
            try:
                api = TikTokAPI(username)
                is_live = False
                try:
                    is_live = api.is_live()
                except Exception as e:
                    logger.error("Error checking live status for %s: %s", username, e)

                if is_live:
                    # Always update online=True when live
                    status_tracker.update_status(username, online=True)

                    if username not in recorders or not recorders[username].is_running():
                        recorder = TikTokLiveRecorder(api, resolution="480p")
                        out_path = recording_output_path(username)
                        ok = recorder.start_recording(out_path)
                        if ok:
                            recorders[username] = recorder
                            status_tracker.set_recording_file(username, out_path)
                            # Mark recording True only after recorder starts
                            status_tracker.update_status(username, recording=True)
                        else:
                            status_tracker.update_status(username, recording=False)

                    # Track live duration by checking time since the user went live
                    live_time = status_tracker.get_status(username).get("last_online")
                    if live_time:
                        live_duration = (datetime.utcnow() - live_time).total_seconds()
                        status_tracker.update_status(username, live_duration=live_duration)
                    else:
                        # First time they went live (initialize)
                        status_tracker.update_status(username, last_online=datetime.utcnow())
                
                else:
                    # Offline: stop recorder if needed
                    status_tracker.update_status(username, online=False, recording=False)
                    rec = recorders.get(username)
                    if rec and rec.is_running():
                        rec.stop_recording()
                        out_file = status_tracker.get_recording_file(username)
                        if out_file and os.path.exists(out_file) and username in uploaders:
                            try:
                                uploaders[username].upload_file(out_file, remote_subfolder=username)
                            except Exception as e:
                                logger.exception("Upload failed for %s: %s", username, e)
                        status_tracker.set_recording_file(username, None)
            except Exception:
                logger.exception("Unhandled error while polling %s", username)
        sleep(POLL_INTERVAL)

Thread(target=poll_loop, daemon=True).start()

@app.route("/")
def index():
    return redirect(url_for("status"))

@app.route("/authorize")
def authorize():
    redirect_uri = OAUTH_REDIRECT or (request.url_root.rstrip("/") + "/oauth2callback")
    auth_url = create_auth_url(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri)
    return render_template("authorize.html", auth_url=auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    redirect_uri = OAUTH_REDIRECT or (request.url_root.rstrip("/") + "/oauth2callback")
    fetch_and_store_credentials(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri, request.url)
    return redirect(url_for("status"))

@app.route("/status")
def status():
    if not os.path.exists(TOKEN_PATH):
        return redirect(url_for("authorize"))

    rows = []
    for username in usernames:
        info = status_tracker.get_status(username)
        rows.append({
            "username": username,
            "last_online": info.get("last_online", "N/A"),
            "live_duration": info.get("live_duration", 0),
            "online": info.get("online", False),
            "recording": info.get("recording", False),
            "recording_file": info.get("recording_file")
        })
    return render_template("status.html", rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
