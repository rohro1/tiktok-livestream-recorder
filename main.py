# main.py
from flask import Flask, redirect, url_for, render_template, session, request
from src.utils.status_tracker import status_tracker
from src.utils.oauth_drive import get_flow, save_credentials, load_credentials
from src.utils.folder_manager import create_folders_for_users
from src.utils.google_drive_uploader import get_drive_service
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Path to your usernames.txt
USERNAMES_FILE = "usernames.txt"

# Load usernames from file
def load_usernames():
    if os.path.exists(USERNAMES_FILE):
        with open(USERNAMES_FILE, "r") as f:
            return [line.strip() for line in f if line.strip()]
    return []

# Initialize status tracker for all users
status_tracker.init_users(load_usernames())

@app.route("/")
def index():
    creds = load_credentials()
    if not creds:
        return redirect(url_for("authorize"))
    return redirect(url_for("status"))

@app.route("/authorize")
def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_credentials(creds)
    return redirect(url_for("status"))

@app.route("/status")
def status():
    return render_template("status.html", statuses=status_tracker.get_status())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
