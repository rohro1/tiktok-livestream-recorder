# main.py
import os
import logging
from flask import Flask, redirect, render_template, request, url_for, jsonify
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from datetime import datetime
from pathlib import Path

# internal imports (use 'src' package)
from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service, TOKEN_PATH
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_api import TikTokAPI
from src.core.tiktok_recorder import TikTokLiveRecorder
from src.utils.google_drive_uploader import GoogleDriveUploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

# Environment / config
PORT = int(os.environ.get("PORT", "10000"))
OAUTH_CREDENTIALS_FILE = os.environ.get("OAUTH_CREDENTIALS_FILE", "credentials.json")
OAUTH_REDIRECT = os.environ.get("OAUTH_REDIRECT")  # https://<your-render>.onrender.com/oauth2callback
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "12"))
DRIVE_ROOT_FOLDER = os.environ.get("DRIVE_ROOT_FOLDER", "TikTokRecordings")
TEMP_DIR = os.environ.get("TEMP_DIR", "/tmp")

# ensure directories
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates")
status = StatusTracker()
recorders = {}         # username -> TikTokLiveRecorder instance
uploader = None        # single GoogleDriveUploader (handles drive root)
executor = ThreadPoolExecutor(max_workers=4)

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

def recording_temp_path(username):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(TEMP_DIR, f"{username}_{ts}.mp4")

def init_drive_if_ready():
    global uploader
    if uploader:
        return
    svc = get_drive_service(OAUTH_CREDENTIALS_FILE, SCOPES)
    if svc:
        uploader = GoogleDriveUploader(svc, drive_folder_root=DRIVE_ROOT_FOLDER)
        logger.info("Initialized GoogleDriveUploader")
    else:
        logger.info("Drive service not ready (no token yet)")

def start_record_async(username, stream_url):
    out_path = recording_temp_path(username)
    def _start():
        try:
            rec = TikTokLiveRecorder(stream_url)
            ok = rec.start_recording(out_path, resolution="480p")
            if ok:
                recorders[username] = rec
                status.set_recording_file(username, out_path)
                status.update_status(username, online=True, recording=True)
                logger.info("Recording started for %s -> %s", username, out_path)
            else:
                logger.warning("Failed to start recorder for %s", username)
                status.update_status(username, online=True, recording=False)
        except Exception:
            logger.exception("Exception when starting recorder for %s", username)
    executor.submit(_start)

def stop_and_upload(username):
    rec = recorders.get(username)
    if rec and rec.is_running():
        logger.info("Stopping recorder for %s", username)
        rec.stop_recording()

    out_file = status.get_recording_file(username)
    status.set_recording_file(username, None)
    status.update_status(username, recording=False)
    # upload if exists
    if out_file and os.path.exists(out_file):
        init_drive_if_ready()
        if uploader:
            # remote subfolder: username/YYYY-MM-DD
            date_folder = datetime.utcnow().strftime("%Y-%m-%d")
            remote_folder = f"{username}/{date_folder}"
            try:
                uploader.upload_file(out_file, remote_subfolder=remote_folder)
                logger.info("Uploaded %s to Drive under %s", out_file, remote_folder)
            except Exception:
                logger.exception("Upload failed for %s", out_file)
        else:
            logger.warning("Uploader not ready, skipping upload for %s", out_file)
        # delete local file to avoid keeping on Render
        try:
            os.remove(out_file)
            logger.info("Deleted local file %s", out_file)
        except Exception:
            logger.exception("Failed to delete local recording %s", out_file)

def poll_once(usernames):
    for username in usernames:
        try:
            api = TikTokAPI(username)
            is_live, stream_url = api.is_live_and_get_stream_url()
            if is_live:
                # update tracker
                status.update_status(username, online=True)
                status.update_live_duration(username)
                # if not recording, start it
                rec = recorders.get(username)
                if not rec or not rec.is_running():
                    # if stream_url not found, we still attempt to start; TikTokLiveRecorder handles missing url failure
                    start_record_async(username, stream_url)
            else:
                # not live — if we were recording, stop and upload
                prev = status.get_status(username)
                if prev.get("online") or prev.get("recording"):
                    # change status and stop recorder
                    status.update_status(username, online=False, recording=False)
                    stop_and_upload(username)
                else:
                    status.update_status(username, online=False, recording=False)
        except Exception:
            logger.exception("Polling error for %s", username)

def poll_loop():
    logger.info("Starting poll loop with interval %s seconds", POLL_INTERVAL)
    while True:
        usernames = read_usernames(USERNAMES_FILE)
        if not usernames:
            logger.info("No usernames to monitor (file empty or missing)")
        init_drive_if_ready()
        poll_once(usernames)
        sleep(POLL_INTERVAL)

# start background poll
from threading import Thread
Thread(target=poll_loop, daemon=True).start()

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
        logger.info("OAuth success — token saved to %s", TOKEN_PATH)
        init_drive_if_ready()
    else:
        logger.warning("OAuth callback did not produce credentials")
    return redirect(url_for("status_page"))

@app.route("/status")
def status_page():
    rows = []
    usernames = read_usernames(USERNAMES_FILE)
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
    logger.info("App starting on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
