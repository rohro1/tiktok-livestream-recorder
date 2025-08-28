import os
import json
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "../../credentials.json")  # Google OAuth client secrets
TOKEN_FILE = os.path.join(BASE_DIR, "../../token.json")              # Where tokens are saved

# Google Drive scope
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Fixed redirect URI (must match your Google Cloud OAuth setup)
REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"


def get_flow():
    """Create a Google OAuth Flow object with fixed redirect URI."""
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )


def set_credentials(credentials):
    """Save Google OAuth credentials to token.json."""
    with open(TOKEN_FILE, "w") as token:
        token.write(credentials.to_json())


def get_credentials():
    """Load saved credentials if they exist and are valid."""
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            return creds
    return None


def get_drive_service():
    """Return an authorized Google Drive API service object."""
    creds = get_credentials()
    if not creds:
        raise Exception("No valid credentials. Please authorize via /authorize.")
    return build("drive", "v3", credentials=creds)
