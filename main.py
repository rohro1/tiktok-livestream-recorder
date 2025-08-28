from flask import Flask, request, redirect, jsonify
from src.utils.oauth_drive import GoogleDriveOAuth
import os

app = Flask(__name__)

# Change these values to match your Google Cloud OAuth app
CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
REDIRECT_URI = "https://e0ea3c89-7858-4fa4-b7d5-1bc54bf48c59-00-1aiz3bpxtehrg.kirk.render.dev/oauth2callback"

gdrive_auth = GoogleDriveOAuth(CREDENTIALS_FILE, SCOPES, REDIRECT_URI)

@app.route("/")
def home():
    auth_url = gdrive_auth.create_auth_url()
    return f'<a href="{auth_url}">Authorize Google Drive Access</a>'

@app.route("/oauth2callback")
def oauth2callback():
    code_url = request.url
    creds = gdrive_auth.fetch_and_store_credentials(code_url)
    if creds:
        return "Authorization successful! Credentials stored."
    else:
        return "Authorization failed."

@app.route("/drive_test")
def drive_test():
    service = gdrive_auth.get_drive_service()
    if service:
        # List first 10 files
        results = service.files().list(pageSize=10, fields="files(id, name)").execute()
        items = results.get("files", [])
        return jsonify(items)
    else:
        return "Drive service not available. Authorize first."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
