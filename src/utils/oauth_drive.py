import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def fetch_and_store_credentials(credentials_file, scopes, redirect_uri, request_url):
    """
    Exchange the authorization code for credentials and save them to token.pkl
    """
    flow = Flow.from_client_secrets_file(
        credentials_file,
        scopes=scopes,
        redirect_uri=redirect_uri
    )
    flow.fetch_token(authorization_response=request_url)
    creds = flow.credentials
    with open("token.pkl", "wb") as f:
        pickle.dump(creds, f)
    return creds

def get_drive_service(credentials=None):
    """
    Return a Google Drive API service object
    """
    if credentials is None:
        if not os.path.exists("token.pkl"):
            return None
        with open("token.pkl", "rb") as f:
            credentials = pickle.load(f)
    service = build("drive", "v3", credentials=credentials)
    return service
