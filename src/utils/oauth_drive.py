import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

class GoogleDriveOAuth:
    def __init__(self, credentials_file, scopes, redirect_uri):
        self.credentials_file = credentials_file
        self.scopes = scopes
        self.redirect_uri = redirect_uri
        self.creds = None

    def create_auth_url(self):
        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        return auth_url

    def fetch_and_store_credentials(self, request_url):
        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        flow.fetch_token(authorization_response=request_url)
        self.creds = flow.credentials
        with open("token.pkl", "wb") as f:
            pickle.dump(self.creds, f)
        return self.creds

    def get_drive_service(self):
        if self.creds is None:
            if not os.path.exists("token.pkl"):
                return None
            with open("token.pkl", "rb") as f:
                self.creds = pickle.load(f)
        service = build("drive", "v3", credentials=self.creds)
        return service
