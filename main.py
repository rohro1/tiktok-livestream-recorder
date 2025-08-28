import os
from flask import Flask, redirect, request, render_template_string
from src.utils.oauth_drive import create_auth_url, fetch_and_store_credentials, get_drive_service

app = Flask(__name__)

# ==== CONFIGURATION ====
CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"

# ==== ROUTES ====
@app.route("/")
def index():
    return """
    <h1>Authorize Google Drive Access</h1>
    <a href="/authorize">Click here to authorize</a>
    """

@app.route("/authorize")
def authorize():
    try:
        auth_url = create_auth_url(CREDENTIALS_FILE, SCOPES, REDIRECT_URI)
        return redirect(auth_url)
    except Exception as e:
        return f"Error generating authorization URL: {e}", 500

@app.route("/oauth2callback")
def oauth2callback():
    try:
        full_url = request.url
        creds = fetch_and_store_credentials(CREDENTIALS_FILE, SCOPES, REDIRECT_URI, full_url)
        # Successfully authorized
        return redirect("/status")
    except Exception as e:
        return f"Authorization failed: {e}", 500

@app.route("/status")
def status():
    # Placeholder status page
    return render_template_string("""
    <h1>TikTok Livestream Recorder Status</h1>
    <p>Google Drive authorization completed!</p>
    <p>Livestream recording functionality will appear here.</p>
    """)

# ==== RUN APP ====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
