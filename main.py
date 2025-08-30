# main.py
import os
import logging
from flask import Flask, redirect, render_template, request, url_for, jsonify
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from datetime import datetime
from pathlib import Path

# local imports
from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service, TOKEN_PATH
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_api import TikTokAPI
from src.core.tiktok_recorder import TikTokLiveRecorder
from src.utils.folder_manager import make_user_folders
from src.utils.google_drive_uploader import GoogleDriveUploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

# Settings from env
PORT = int(os.environ.get("PORT", "10000"))
OAUTH_CREDENTIALS_FILE = os.environ.get("OAUTH_CREDENTIALS_FILE", "credentials.json")
OAUTH_REDIRECT = os.environ.get("OAUTH_REDIRECT")  # if set in Render
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "recordings")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "12"))  # seconds
DRIVE_ROOT_FOLDER = os.environ.get("DRIVE_ROOT_FOLDER", "TikTokRecordings")

# prepare
app = Flask(__name__, template_folder="templates")
Path(RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)

# helper to read usernames
def read_usernames(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if u and not u.startswith("#"):
                    out.append(u)
    except FileNotFoundError:
        logger.warning("Usernames file not found: %s", path)
    return out

usernames = read_usernames(USERNAMES_FILE)
status = StatusTracker()
recorders = {}         # username -> TikTokLiveRecorder
uploaders = {}         # username -> GoogleDriveUploader
executor = ThreadPoolExecutor(max_workers=4)

def recording_output_path(username):
    user_dir = Path(RECORDINGS_DIR) / username
    user_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return str(user_dir / f"{username}_{ts}.mp4")

def try_init_drive():
    service = get_drive_service(OAUTH_CREDENTIALS_FILE, SCOPES)
    if not service:
        logger.warning("Drive service unavailable (no credentials yet)")
        return
    uploader = GoogleDriveUploader(service, drive_folder_root=DRIVE_ROOT_FOLDER)
    for u in usernames:
        uploaders[u] = uploader  # single uploader instance can handle multiple users

def poll_once():
    global usernames
    # refresh usernames from file periodically so you can add entries without redeploy
    usernames = read_usernames(USERNAMES_FILE) or usernames
    make_user_folders(usernames, RECORDINGS_DIR)
    # ensure uploader if credentials present
    if not uploaders:
        try_init_drive()

    for username in usernames:
        try:
            api = TikTokAPI(username)
            is_live, stream_url = api.is_live_and_get_stream_url()
            if is_live:
                status.update_status(username, online=True)
                # start recorder if not running
                r = recorders.get(username)
                if not r or not r.is_running():
                    out_path = recording_output_path(username)
                    # start asynchronously so loop is nonblocking
                    def start_record(username=username, stream_url=stream_url, out_path=out_path):
                        rec = TikTokLiveRecorder(stream_url)
                        ok = rec.start_recording(out_path, resolution="480p")
                        if ok:
                            recorders[username] = rec
                            status.set_recording_file(username, out_path)
                            status.update_status(username, recording=True)
                            logger.info("Started recording %s -> %s", username, out_path)
                        else:
                            status.update_status(username, recording=False)
                    executor.submit(start_record)
                else:
                    # update duration
                    status.update_live_duration(username)
            else:
                # if previously online, stop recorder
                status.update_status(username, online=False)
                rec = recorders.get(username)
                if rec and rec.is_running():
                    logger.info("Stopping recorder for %s", username)
                    rec.stop_recording()
                    out_file = status.get_recording_file(username)
                    if out_file and os.path.exists(out_file) and uploaders.get(username):
                        try:
                            uploaders[username].upload_file(out_file, remote_subfolder=username)
                        except Exception as e:
                            logger.exception("Upload failed for %s: %s", username, e)
                    status.set_recording_file(username, None)
                    status.update_status(username, recording=False)
        except Exception as e:
            logger.exception("Polling error for %s: %s", username, e)

def poll_loop():
    logger.info("Starting poll loop (interval=%s)", POLL_INTERVAL)
    while True:
        try:
            poll_once()
        except Exception:
            logger.exception("Unhandled exception in poll loop")
        sleep(POLL_INTERVAL)

# launch background poll loop
from threading import Thread
Thread(target=poll_loop, daemon=True).start()

# routes
@app.route("/")
def index():
    return redirect(url_for("status_page"))

@app.route("/authorize")
def authorize():
    redirect_uri = OAUTH_REDIRECT or (request.url_root.rstrip("/") + "/oauth2callback")
    auth_url = create_auth_url(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri)
    return render_template("authorize.html", auth_url=auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    redirect_uri = OAUTH_REDIRECT or (request.url_root.rstrip("/") + "/oauth2callback")
    full_url = request.url
    creds = fetch_and_store_credentials(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri, full_url)
    if creds:
        logger.info("OAuth success — credentials saved to %s", TOKEN_PATH)
        # re-init uploader with new credentials
        try_init_drive()
    else:
        logger.warning("OAuth callback did not produce credentials")
    return redirect(url_for("status_page"))

@app.route("/status")
def status_page():
    rows = []
    for username in usernames:
        st = status.get_status(username)
        rows.append({
            "username": username,
            "last_online": st.get("last_online") or "N/A",
            "live_duration": st.get("live_duration", 0),
            "online": st.get("online", False),
            "recording": st.get("recording", False),
            "recording_file": st.get("recording_file"),
        })
    if request.args.get("json") == "1":
        return jsonify({r["username"]: r for r in rows})
    return render_template("status.html", rows=rows)

if __name__ == "__main__":
    logger.info("Starting Flask on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
