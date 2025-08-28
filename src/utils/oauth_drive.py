# src/utils/oauth_drive.py

import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Path to store credentials
CREDENTIALS_FILE = "credentials.json"  # Your OAuth client credentials file
TOKEN_PICKLE = "token.pickle"

# Redirect URI must match what is set in Google Cloud Console
REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_flow():
    """Create a new OAuth2 flow instance."""
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def save_credentials(credentials):
    """Save user credentials to token.pickle."""
    with open(TOKEN_PICKLE, "wb") as token:
        pickle.dump(credentials, token)


def get_drive_service():
    """Return an authorized Google Drive API service instance."""
    creds = None
    # Load saved credentials
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as token:
            creds = pickle.load(token)

    # Refresh token if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)

    # Build Drive API service
    if creds:
        return build("drive", "v3", credentials=creds)
    else:
        return None
