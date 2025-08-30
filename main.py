import os
import logging
from flask import Flask, redirect, render_template, request, url_for, abort
from threading import Thread
from time import sleep
from datetime import datetime
from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service, TOKEN_PATH
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_api import TikTokAPI
from src.core.tiktok_recorder import TikTokLiveRecorder
from src.utils.folder_manager import make_user_folders
from src.utils.google_drive_uploader import GoogleDriveUploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

PORT = int(os.environ.get("PORT", 10000))
CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USERNAMES_FILE = "usernames.txt"
RECORDINGS_DIR = "recordings"
POLL_INTERVAL = 15

app = Flask(__name__, template_folder="templates")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

def read_usernames(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [u.strip() for u in f if u.strip()]
    except FileNotFoundError:
        return []

usernames = read_usernames(USERNAMES_FILE)
status_tracker = StatusTracker()
recorders = {}
uploaders = {}

def recording_output_path(username):
    os.makedirs(os.path.join(RECORDINGS_DIR, username), exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(RECORDINGS_DIR, username, f"{username}_{ts}.mp4")

def poll_loop():
    logger.info("Polling started (interval=%s)", POLL_INTERVAL)
    make_user_folders(usernames, RECORDINGS_DIR)
    drive_service = get_drive_service(CREDENTIALS_FILE, SCOPES)
    if drive_service:
        for u in usernames:
            uploaders[u] = GoogleDriveUploader(drive_service, "TikTokRecordings")

    while True:
        for username in usernames:
            try:
                api = TikTokAPI(username)
                if api.is_live():
                    status_tracker.update_status(username, online=True)
                    if username not in recorders or not recorders[username].is_running():
                        out_path = recording_output_path(username)
                        recorder = TikTokLiveRecorder(api, "480p")
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
                                uploaders[username].upload_file(out_file, username)
                            except Exception as e:
                                logger.exception("Upload failed: %s", e)
                        status_tracker.set_recording_file(username, None)
                        status_tracker.update_status(username, recording=False)
            except Exception as e:
                logger.exception("Poll error: %s", e)
        sleep(POLL_INTERVAL)

Thread(target=poll_loop, daemon=True).start()

@app.route("/")
def index():
    return redirect(url_for("status"))

@app.route("/authorize")
def authorize():
    if os.path.exists(TOKEN_PATH):
        return redirect(url_for("status"))
    redirect_uri = request.url_root.rstrip("/") + "/oauth2callback"
    auth_url = create_auth_url(CREDENTIALS_FILE, SCOPES, redirect_uri)
    return render_template("authorize.html", auth_url=auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    if os.path.exists(TOKEN_PATH):
        return redirect(url_for("status"))
    redirect_uri = request.url_root.rstrip("/") + "/oauth2callback"
    creds = fetch_and_store_credentials(CREDENTIALS_FILE, SCOPES, redirect_uri, request.url)
    if creds:
        logger.info("OAuth success — saved token.json")
    return redirect(url_for("status"))

@app.route("/status")
def status():
    authorized = os.path.exists(TOKEN_PATH)
    data = []
    for username in usernames:
        st = status_tracker.get_status(username)
        data.append({
            "username": username,
            "online": st.get("online", False),
            "recording": st.get("recording", False),
            "last_online": st.get("last_online") or "N/A",
            "file": st.get("recording_file"),
        })
    return render_template("status.html", rows=data, authorized=authorized)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
