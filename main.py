import os
import threading
import time
from flask import Flask, redirect, jsonify
from datetime import datetime
from src.core.tiktok_api import is_user_live
from src.core.recorder import record_stream
from src.utils.status_tracker import tracker
from src.utils.folder_manager import get_or_create_user_folder
from src.utils.google_drive_uploader import upload_file_to_drive

CHECK_INTERVAL = 300  # 5 minutes
app = Flask(__name__)

def monitor_user(username):
    while True:
        try:
            print(f"[CHECK] Checking if {username} is live...")
            if is_user_live(username):
                if not tracker.is_recording(username):
                    tracker.set_online(username, True)
                    tracker.start_recording(username)

                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    base_folder = get_or_create_user_folder(username)
                    date_folder = os.path.join(base_folder, datetime.now().strftime("%m-%d-%Y"))
                    os.makedirs(date_folder, exist_ok=True)
                    output_file = os.path.join(date_folder, f"{timestamp}.mp4")

                    print(f"[RECORDING] Actively recording {username} -> {output_file}")
                    record_stream(username, output_file)
                    tracker.stop_recording(username)

                    # Upload to Google Drive
                    upload_file_to_drive(output_file, username)
                else:
                    print(f"[INFO] {username} is already being recorded.")
            else:
                tracker.set_offline(username, False)
        except Exception as e:
            print(f"[ERROR] Failed to check or record {username}: {e}")
        time.sleep(CHECK_INTERVAL)

def start_monitoring():
    if not os.path.exists("usernames.txt"):
        print("[ERROR] usernames.txt not found.")
        return

    with open("usernames.txt", "r") as f:
        usernames = [line.strip() for line in f if line.strip()]

    for username in usernames:
        tracker.initialize(username)
        threading.Thread(target=monitor_user, args=(username,), daemon=True).start()

@app.route("/")
def index():
    return redirect("/status")

@app.route("/status")
def status():
    return jsonify(tracker.get_all_status())

if __name__ == "__main__":
    start_monitoring()
    app.run(host="0.0.0.0", port=10000)
