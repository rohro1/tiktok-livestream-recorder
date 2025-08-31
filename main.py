# main.py
import os
import logging
from flask import Flask, redirect, render_template, request, url_for, jsonify
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from datetime import datetime
from pathlib import Path
from threading import Thread

# local imports (package style)
from src.utils.oauth_drive import create_auth_url, fetch_and_return_credentials_json, get_drive_service
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_api import TikTokAPI
from src.core.tiktok_recorder import TikTokLiveRecorder
from src.utils.folder_manager import make_user_folders
from src.utils.google_drive_uploader import GoogleDriveUploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

# Settings (set in Render environment)
PORT = int(os.environ.get("PORT", "10000"))
OAUTH_CREDENTIALS_FILE = os.environ.get("OAUTH_CREDENTIALS_FILE", "credentials.json")  # client secret file path (keep secret)
OAUTH_REDIRECT = os.environ.get("OAUTH_REDIRECT")  # e.g. https://<your-render>.onrender.com/oauth2callback
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/tmp/recordings")  # tmp on render; we delete after upload
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "12"))
DRIVE_ROOT_FOLDER = os.environ.get("DRIVE_ROOT_FOLDER", "TikTokRecordings")

Path(RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates")

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
recorders = {}     # username -> TikTokLiveRecorder instance
executor = ThreadPoolExecutor(max_workers=4)
uploader = None    # GoogleDriveUploader singleton (constructed when creds available)

def ensure_uploader():
    global uploader
    if uploader:
        return
    service = get_drive_service(OAUTH_CREDENTIALS_FILE, SCOPES)
    if service:
        uploader = GoogleDriveUploader(service, drive_folder_root=DRIVE_ROOT_FOLDER)
        logger.info("Drive uploader initialized")
    else:
        logger.info("Drive service not available yet (no token)")

def recording_output_path(username):
    user_dir = Path(RECORDINGS_DIR) / username
    user_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return str(user_dir / f"{username}_{ts}.mp4")

def poll_once():
    global usernames
    usernames = read_usernames(USERNAMES_FILE) or usernames
    make_user_folders(usernames, RECORDINGS_DIR)
    ensure_uploader()

    for username in usernames:
        try:
            api = TikTokAPI(username)
            is_live, stream_url = api.is_live_and_get_stream_url()
            logger.debug("User %s live=%s url=%s", username, is_live, bool(stream_url))
            if is_live:
                status.update_status(username, online=True)
                status.update_live_duration(username)
                rec = recorders.get(username)
                if not rec or not rec.is_running():
                    out_path = recording_output_path(username)
                    def start_record(username=username, stream_url=stream_url, out_path=out_path):
                        # If we don't have a direct stream_url, try to let yt-dlp/recorder attempt
                        rec_local = TikTokLiveRecorder(stream_url)
                        ok = rec_local.start_recording(out_path, resolution="480p")
                        if ok:
                            recorders[username] = rec_local
                            status.set_recording_file(username, out_path)
                            status.update_status(username, recording=True)
                            logger.info("Started recording %s -> %s", username, out_path)
                        else:
                            status.update_status(username, recording=False)
                    executor.submit(start_record)
                else:
                    status.update_live_duration(username)
            else:
                status.update_status(username, online=False)
                rec = recorders.get(username)
                if rec and rec.is_running():
                    logger.info("Stopping recorder for %s", username)
                    rec.stop_recording()
                    out_file = status.get_recording_file(username)
                    status.set_recording_file(username, None)
                    status.update_status(username, recording=False)
                    # upload immediately and remove local file
                    if out_file and uploader:
                        try:
                            uploader.upload_file(out_file, remote_subfolder=username)
                            logger.info("Uploaded and removing local file %s", out_file)
                        except Exception:
                            logger.exception("Upload failed for %s", username)
                        finally:
                            try:
                                if out_file and os.path.exists(out_file):
                                    os.remove(out_file)
                            except Exception:
                                logger.exception("Failed to remove local file %s", out_file)
        except Exception:
            logger.exception("Error polling %s", username)

def poll_loop():
    logger.info("Starting poll loop (interval=%s)", POLL_INTERVAL)
    while True:
        try:
            poll_once()
        except Exception:
            logger.exception("Unhandled exception in poll loop")
        sleep(POLL_INTERVAL)

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
    # This will exchange code and return the token JSON string (but won't save it on disk)
    creds_json = fetch_and_return_credentials_json(OAUTH_CREDENTIALS_FILE, SCOPES, redirect_uri, full_url)
    if creds_json:
        # Important: we instruct the user to add this JSON to their Render secret named TOKEN_JSON
        return (
            "<h2>OAuth success</h2>"
            "<p>DO NOT commit this to GitHub. Copy the JSON below and create a Render secret named <code>TOKEN_JSON</code> with its value.</p>"
            f"<textarea cols=100 rows=20>{creds_json}</textarea>"
            "<p>After adding the TOKEN_JSON secret, redeploy or restart the service so it picks up the token.</p>"
            f"<p><a href='{url_for('status_page')}'>Go to status</a></p>"
        )
    else:
        return "<p>OAuth failed or missing code param. Check logs.</p>"

@app.route("/status")
def status_page():
    rows = []
    for username in usernames:
        st = status.get_status(username)
        profile_url = f"https://www.tiktok.com/@{username}"
        live_url = f"https://www.tiktok.com/@{username}/live"
        rows.append({
            "username": username,
            "profile_url": profile_url,
            "live_url": live_url,
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
