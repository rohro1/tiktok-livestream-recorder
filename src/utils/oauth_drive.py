# src/utils/oauth_drive.py
import os
import logging
import json
from urllib.parse import urlencode, urlparse, parse_qs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger("oauth_drive")
TOKEN_PATH = "token.json"

def create_auth_url(client_secrets_file, scopes, redirect_uri):
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return auth_url

def fetch_and_store_credentials(client_secrets_file, scopes, redirect_uri, full_request_url):
    # Parse code param from full_request_url and exchange
    parsed = urlparse(full_request_url)
    qs = parse_qs(parsed.query)
    if "code" not in qs:
        logger.warning("OAuth callback missing code")
        return None
    code = qs["code"][0]
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    # save token.json to disk (Render runtime ephemeral but token file is useful between restarts)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    return creds

def get_drive_service(client_secrets_file, scopes):
    # if token exists, load it
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
    else:
        # try to load from environment-mounted credentials (Render secrets)
        # If client_secrets_file is a path (e.g. credentials.json) it should be present in project root
        if not os.path.exists(client_secrets_file):
            logger.debug("client_secrets_file missing: %s", client_secrets_file)
            return None
        # No token.json; the app must call /authorize for user to create it.
        return None

    if not creds or not creds.valid:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
        except Exception:
            return None
    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service
    except Exception:
        logger.exception("Failed to build drive service")
        return None
