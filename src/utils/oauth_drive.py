# src/utils/oauth_drive.py
import os
import pickle
import logging
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger("oauth-drive")
logger.setLevel(logging.INFO)

TOKEN_PATH = os.path.join(os.getcwd(), "token.pkl")

def create_auth_url(credentials_file, scopes, redirect_uri):
    """
    Build an OAuth URL for Google drive.
    """
    flow = Flow.from_client_secrets_file(
        credentials_file,
        scopes=scopes,
        redirect_uri=redirect_uri
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url

def fetch_and_store_credentials(credentials_file, scopes, redirect_uri, request_url):
    """
    Given the full request_url (which contains ?code=...),
    fetch token and store to token.pkl.
    """
    try:
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=scopes,
            redirect_uri=redirect_uri
        )
        flow.fetch_token(authorization_response=request_url)
        creds = flow.credentials
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
        logger.info("Saved credentials to %s", TOKEN_PATH)
        return creds
    except Exception:
        logger.exception("Failed to fetch/store credentials")
        return None

def load_credentials():
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
            return creds
    except Exception:
        logger.exception("Failed to load credentials from %s", TOKEN_PATH)
        return None

def get_drive_service(credentials=None):
    """
    Returns a google drive v3 service object if credentials are present.
    """
    creds = credentials or load_credentials()
    if not creds:
        return None
    try:
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception:
        logger.exception("Failed to build Google Drive service")
        return None
