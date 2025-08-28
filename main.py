from flask import Flask, redirect, request, url_for
from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service

app = Flask(__name__)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = "credentials.json"

@app.route("/")
def index():
    return '<a href="/authorize">Authorize Google Drive Access</a>'

@app.route("/authorize")
def authorize():
    auth_url = create_auth_url(CREDENTIALS_FILE, SCOPES)
    return redirect(auth_url)

@app.route("/callback")
def callback():
    request_url = request.url
    creds = fetch_and_store_credentials(CREDENTIALS_FILE, SCOPES, request_url)
    return "Authorization successful! You can close this window."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
