import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

TOKEN_PATH = "token.pkl"

def create_auth_url(credentials_file, scopes, redirect_uri):
    flow = Flow.from_client_secrets_file(credentials_file, scopes=scopes, redirect_uri=redirect_uri)
    return flow.authorization_url()[0]

def fetch_and_store_credentials(credentials_file, scopes, redirect_uri, full_url):
    flow = Flow.from_client_secrets_file(credentials_file, scopes=scopes, redirect_uri=redirect_uri)
    code = flow.fetch_token(authorization_response=full_url)
    creds = flow.credentials
    with open(TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)
    return creds

def get_drive_service(credentials_file=None, scopes=None):
    import pickle
    if not os.path.exists(TOKEN_PATH):
        return None
    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)
    return build("drive", "v3", credentials=creds)
