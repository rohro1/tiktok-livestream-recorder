# src/utils/oauth_drive.py
import os
import logging
from urllib.parse import urlparse, parse_qs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

logger = logging.getLogger("oauth_drive")
TOKEN_PATH = "token.json"

def create_auth_url(client_secrets_file, scopes, redirect_uri):
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return auth_url

def fetch_and_store_credentials(client_secrets_file, scopes, redirect_uri, full_request_url):
    parsed = urlparse(full_request_url)
    qs = parse_qs(parsed.query)
    if "code" not in qs:
        logger.warning("OAuth callback missing code")
        return None
    code = qs["code"][0]
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    return creds

def get_drive_service(client_secrets_file, scopes):
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
    else:
        # no saved token
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # persist refreshed token
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        except Exception:
            logger.exception("Failed to refresh credentials")
            return None
    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service
    except Exception:
        logger.exception("Failed to build drive service")
        return None
