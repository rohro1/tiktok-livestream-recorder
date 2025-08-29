import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import pickle

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"
REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_flow():
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

def save_credentials(creds):
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

def load_credentials():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            return pickle.load(f)
    return None
