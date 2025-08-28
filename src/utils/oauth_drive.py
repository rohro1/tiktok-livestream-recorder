import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Path to store token
TOKEN_PICKLE = "token.pickle"

# Your redirect URI on Render
REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"

# Scopes for Google Drive
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_flow():
    """Create OAuth Flow for Google Drive."""
    return Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def save_credentials(credentials):
    """Save user credentials to token.pickle."""
    with open(TOKEN_PICKLE, "wb") as token:
        pickle.dump(credentials, token)


def load_credentials():
    """Load stored user credentials if available and valid."""
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as token:
            creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)

    return creds


def get_drive_service():
    """Return Google Drive API service if authorized, else None."""
    creds = load_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)
