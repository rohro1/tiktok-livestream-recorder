import os
import threading
import time
from flask import Flask, render_template
from datetime import datetime
from TikTokLiveRecorder.src.core.tiktok_api import TikTokAPI
from TikTokLiveRecorder.src.core.tiktok_recorder import record_stream
from TikTokLiveRecorder.src.utils.status_tracker import status_tracker
from TikTokLiveRecorder.src.utils.upload_to_drive import upload_file_to_drive
from TikTokLiveRecorder.src.utils.google_drive_setup import get_or_create_folder

app = Flask(__name__)

USERNAME_FILE = "usernames.txt"
CHECK_INTERVAL = 300  # 5 minutes
BASE_RECORD_DIR = "recordings"
drive_folder_cache = {}

def monitor_user(username):
    api = TikTokAPI()
    user_folder_id = drive_folder_cache.get(username) or get_or_create_folder(username)
    drive_folder_cache[username] = user_folder_id

    now = datetime.now()
    date_folder_name = now.strftime("%Y-%m-%d")
    full_path = os.path.join(BASE_RECORD_DIR, username, date_folder_name)
    os.makedirs(full_path, exist_ok=True)

    try:
        if api.is_live(username):
            start_time = time.time()
            record_stream(username, full_path)
            duration = time.time() - start_time
            status_tracker.update_status(username, True, time.strftime("%H:%M:%S", time.gmtime(duration)))

            for file in os.listdir(full_path):
                file_path = os.path.join(full_path, file)
                if os.path.isfile(file_path):
                    upload_file_to_drive(file_path, username, date_folder_name)
        else:
            status_tracker.update_status(username, False)
    except Exception as e:
        print(f"[ERROR] Monitoring {username} failed: {e}")
        status_tracker.update_status(username, False)

def monitor_usernames():
    known_usernames = set()

    while True:
        if os.path.exists(USERNAME_FILE):
            with open(USERNAME_FILE) as f:
                usernames = set(line.strip() for line in f if line.strip())
        else:
            usernames = set()

        for username in usernames:
            threading.Thread(target=monitor_user, args=(username,), daemon=True).start()

        known_usernames = usernames
        time.sleep(CHECK_INTERVAL)

@app.route("/status")
def status():
    return render_template("status.html", statuses=status_tracker.get_status(), now=datetime.now())

if __name__ == "__main__":
    threading.Thread(target=monitor_usernames, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)