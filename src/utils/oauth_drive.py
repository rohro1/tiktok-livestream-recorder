import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Set your redirect URI for Render
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://tiktok-livestream-recorder.onrender.com/callback")
TOKEN_FILE = "token.pkl"

def create_auth_url(credentials_file, scopes):
    flow = Flow.from_client_secrets_file(
        credentials_file,
        scopes=scopes,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url

def fetch_and_store_credentials(credentials_file, scopes, request_url):
    flow = Flow.from_client_secrets_file(
        credentials_file,
        scopes=scopes,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(authorization_response=request_url)
    creds = flow.credentials
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)
    return creds

def get_drive_service(credentials=None):
    if credentials is None:
        if not os.path.exists(TOKEN_FILE):
            return None
        with open(TOKEN_FILE, "rb") as f:
            credentials = pickle.load(f)
    service = build("drive", "v3", credentials=credentials)
    return service
