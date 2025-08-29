# main.py
from flask import Flask, redirect, url_for, request, render_template
from src.utils.oauth_drive import get_flow, save_credentials, load_credentials, get_drive_service
from src.utils.folder_manager import create_folders_for_users
from src.utils.status_tracker import status_tracker
from src.TikTokLiveRecorder.src.core.tiktok_api import TikTokAPI
from src.TikTokLiveRecorder.src.core.tiktok_recorder import TikTokLiveRecorder
from googleapiclient.http import MediaFileUpload
import os
import threading
import time
from datetime import datetime

app = Flask(__name__)

USERNAMES_FILE = "usernames.txt"
folder_ids = {}
DRIVE_SERVICE = None

# -------------------- UTILITIES --------------------

def read_usernames():
    if not os.path.exists(USERNAMES_FILE):
        return []
    with open(USERNAMES_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def init_drive_service():
    global DRIVE_SERVICE
    creds = load_credentials()
    if creds:
        DRIVE_SERVICE = get_drive_service(creds)

def update_folders():
    global folder_ids
    while True:
        usernames = read_usernames()
        try:
            folder_ids = create_folders_for_users(usernames)
        except Exception as e:
            print("Error updating folders:", e)
        time.sleep(300)

# -------------------- RECORDING --------------------

def record_user_livestream(username):
    api = TikTokAPI(username)
    recorder = TikTokLiveRecorder(api, resolution="480p")
    date_folder = datetime.now().strftime("%Y-%m-%d")

    while True:
        try:
            if api.is_live():
                status_tracker.update(
                    username,
                    last_online=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    online=True,
                    recording_duration=0
                )

                user_folder_id = folder_ids.get(username)
                if not user_folder_id:
                    time.sleep(10)
                    continue

                filename = f"{username}_{int(time.time())}.mp4"
                local_path = os.path.join("recordings", username, date_folder)
                os.makedirs(local_path, exist_ok=True)
                full_path = os.path.join(local_path, filename)

                recorder.start_recording(output_path=full_path)
                start_time = time.time()

                while api.is_live():
                    elapsed = int(time.time() - start_time)
                    status_tracker.update(username, online=True, recording_duration=elapsed)
                    time.sleep(5)

                recorder.stop_recording()
                status_tracker.update(username, online=False)

                if DRIVE_SERVICE:
                    upload_to_drive(username, date_folder, full_path)
            else:
                status_tracker.update(username, online=False)
                time.sleep(30)

        except Exception as e:
            print(f"Error recording {username}: {e}")
            time.sleep(30)

def upload_to_drive(username, date_folder, file_path):
    user_folder_id = folder_ids.get(username)
    if not user_folder_id:
        return

    # Ensure date folder exists
    query = f"'{user_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{date_folder}'"
    subfolders = DRIVE_SERVICE.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    if subfolders['files']:
        date_folder_id = subfolders['files'][0]['id']
    else:
        folder_metadata = {'name': date_folder, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [user_folder_id]}
        folder = DRIVE_SERVICE.files().create(body=folder_metadata, fields='id').execute()
        date_folder_id = folder['id']

    # Upload recording
    file_metadata = {'name': os.path.basename(file_path), 'parents': [date_folder_id]}
    media = MediaFileUpload(file_path, mimetype='video/mp4')
    DRIVE_SERVICE.files().create(body=file_metadata, media_body=media, fields='id').execute()

# -------------------- ROUTES --------------------

@app.route("/")
def index():
    creds = load_credentials()
    if creds is None:
        return redirect(url_for("authorize"))
    return redirect(url_for("status"))

@app.route("/authorize")
def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    return render_template("authorize.html", auth_url=auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_credentials(creds)
    init_drive_service()

    # Start livestream threads after auth
    for user in read_usernames():
        threading.Thread(target=record_user_livestream, args=(user,), daemon=True).start()
    return redirect(url_for("status"))

@app.route("/status")
def status():
    usernames = read_usernames()
    statuses = {}
    for username in usernames:
        data = status_tracker.get(username, {})
        statuses[username] = {
            "last_online": data.get("last_online", "N/A"),
            "live_duration": data.get("live_duration", 0),
            "online": data.get("online", False),
            "recording_duration": data.get("recording_duration", 0),
            "recording_status": "Recording" if data.get("online", False) else "Not Recording"
        }
    return render_template("status.html", statuses=statuses)

# -------------------- MAIN --------------------

if __name__ == "__main__":
    init_drive_service()
    threading.Thread(target=update_folders, daemon=True).start()

    # Start threads for each user at startup if credentials exist
    if DRIVE_SERVICE:
        for user in read_usernames():
            threading.Thread(target=record_user_livestream, args=(user,), daemon=True).start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
