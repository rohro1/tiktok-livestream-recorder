# src/utils/oauth_drive.py
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import pickle

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pkl"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_flow():
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ.get("RENDER_EXTERNAL_URL", "") + "/oauth2callback"
    )

def save_credentials(creds):
    with open(TOKEN_FILE, "wb") as token:
        pickle.dump(creds, token)

def load_credentials():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            return pickle.load(token)
    return None

def get_drive_service():
    creds = load_credentials()
    if not creds:
        raise Exception("No credentials found.")
    return build("drive", "v3", credentials=creds)
