# src/utils/oauth_drive.py
import os
import pickle
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "token.pkl")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service():
    """
    Load credentials from TOKEN_FILE (created by main.py during OAuth flow),
    refresh if expired, and return a Drive v3 service object.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds:
        raise RuntimeError("No stored Google credentials found. Visit /authorize to connect Google Drive.")

    # Refresh if needed
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # persist refreshed creds
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    if not creds.valid:
        raise RuntimeError("Stored credentials are not valid. Reconnect via /authorize.")

    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return service
