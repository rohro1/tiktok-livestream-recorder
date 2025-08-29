# main.py
from flask import Flask, redirect, url_for, request, render_template
from src.utils.oauth_drive import get_flow, save_credentials, load_credentials
from src.utils.folder_manager import create_folders_for_users
from src.utils.status_tracker import status_tracker
import os
import threading
import time

app = Flask(__name__)

USERNAMES_FILE = "usernames.txt"
folder_ids = {}

def read_usernames():
    if not os.path.exists(USERNAMES_FILE):
        return []
    with open(USERNAMES_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def update_folders():
    global folder_ids
    while True:
        usernames = read_usernames()
        try:
            folder_ids = create_folders_for_users(usernames)
        except Exception as e:
            print("Error updating folders:", e)
        time.sleep(300)  # every 5 min

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
            "recording_duration": data.get("recording_duration", 0)
        }
    return render_template("status.html", statuses=statuses)

if __name__ == "__main__":
    threading.Thread(target=update_folders, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
