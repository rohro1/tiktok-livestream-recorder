# main.py
from flask import Flask, redirect, request, session
from google_auth_oauthlib.flow import Flow
from flask_session import Session
import os
import pickle
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok-recorder")

app = Flask(__name__)

# ---------- Config ----------
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_this_to_a_random_value")
app.config["SESSION_TYPE"] = "filesystem"                # store session server-side so state isn't lost
app.config["SESSION_FILE_DIR"] = os.environ.get("SESSION_FILE_DIR", "/tmp/flask_session")
app.config["SESSION_PERMANENT"] = False
Session(app)

# Google OAuth settings
DEFAULT_CLIENT_SECRETS_PATH = "/etc/secrets/credentials.json"
GOOGLE_CLIENT_SECRETS_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRETS_FILE",
    DEFAULT_CLIENT_SECRETS_PATH if os.path.exists(DEFAULT_CLIENT_SECRETS_PATH) else "credentials.json"
)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "token.pkl")
REDIRECT_ROUTE = "/oauth2callback"

# ---------- Helpers ----------
def get_redirect_uri():
    # Build a redirect URI that matches your Render domain's /oauth2callback
    return request.url_root.rstrip("/") + REDIRECT_ROUTE

# ---------- Routes ----------
@app.route("/")
def index():
    connected = os.path.exists(TOKEN_FILE)
    return (
        f"✅ TikTok Recorder running. Drive connected: {connected}. "
        f"<a href='/authorize'>Connect Google Drive</a> | <a href='/logout'>Disconnect</a>"
    )

@app.route("/authorize")
def authorize():
    # Start OAuth flow
    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=get_redirect_uri()
    )
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    session["state"] = state
    logger.info("Redirecting user to Google auth URL")
    return redirect(auth_url)

@app.route(REDIRECT_ROUTE)
def oauth2callback():
    state = session.get("state")
    if not state:
        return "Missing OAuth state in session. Start at /authorize.", 400

    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=get_redirect_uri()
    )
    # Exchange code for tokens
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # Persist credentials to disk for use by the background recorder/uploader
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

    session.pop("state", None)
    logger.info("OAuth success — credentials saved to %s", TOKEN_FILE)
    return "🎉 Google Drive connected successfully! You can close this tab."

@app.route("/logout")
def logout():
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            logger.info("Removed token file %s", TOKEN_FILE)
    except Exception:
        logger.exception("Failed to remove token file")
    session.clear()
    return "Logged out and token cleared. Reconnect at /authorize."

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
