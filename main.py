from flask import Flask, redirect, request, render_template
from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service

app = Flask(__name__)

CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

@app.route("/")
def index():
    # Show button to authorize Google Drive
    return render_template("authorize.html")  # a simple HTML page with "Authorize Google Drive Access" button linking to /authorize

@app.route("/authorize")
def authorize():
    auth_url = create_auth_url(CREDENTIALS_FILE, SCOPES)
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    request_url = request.url
    creds = fetch_and_store_credentials(CREDENTIALS_FILE, SCOPES, request_url)
    # Redirect to /status after successful authorization
    return redirect("/status")

@app.route("/status")
def status():
    # Example: check if Google Drive service is available
    service = get_drive_service()
    if service:
        status_message = "Google Drive authorized and ready."
    else:
        status_message = "Google Drive not authorized."
    return f"<h1>Livestream Recorder Status</h1><p>{status_message}</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
