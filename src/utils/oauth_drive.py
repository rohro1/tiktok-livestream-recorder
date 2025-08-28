import os
import pickle
from flask import session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# OAuth 2.0 settings
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRETS_FILE = "credentials.json"

def get_flow():
    """
    Create the OAuth Flow object configured for Render deployment.
    """
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri="https://tiktok-livestream-recorder.onrender.com/oauth2callback"
    )

def get_drive_service():
    """
    Returns an authorized Drive API service instance.
    Uses session-stored credentials if available.
    """
    creds = None

    # Load from session if present
    if "credentials" in session:
        creds = pickle.loads(session["credentials"])

    # If no valid creds, redirect to /authorize
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            return redirect(url_for("authorize"))

    # Save back refreshed creds
    session["credentials"] = pickle.dumps(creds)

    # Build Drive client
    return build("drive", "v3", credentials=creds)
