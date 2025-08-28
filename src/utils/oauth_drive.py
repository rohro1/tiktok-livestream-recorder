import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

CLIENT_SECRETS_FILE = "credentials.json"
TOKEN_FILE = "token.pkl"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ.get("OAUTH_REDIRECT_URI")
    )

def save_credentials(creds):
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

def load_credentials():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "rb") as f:
        return pickle.load(f)

def get_drive_service():
    creds = load_credentials()
    if not creds:
        raise Exception("No Google credentials found. Authorize first.")
    return build("drive", "v3", credentials=creds)
