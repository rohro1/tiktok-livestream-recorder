# src/utils/oauth_drive.py
import os
import logging
import json
from urllib.parse import urlparse, parse_qs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

logger = logging.getLogger("oauth_drive")

def create_auth_url(client_secrets_file, scopes, redirect_uri):
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return auth_url

def fetch_and_return_credentials_json(client_secrets_file, scopes, redirect_uri, full_request_url):
    parsed = urlparse(full_request_url)
    qs = parse_qs(parsed.query)
    if "code" not in qs:
        logger.warning("OAuth callback missing code")
        return None
    code = qs["code"][0]
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        creds_json = creds.to_json()
        # DO NOT write to disk. Return JSON to instruct user to save it as a secret.
        return creds_json
    except Exception:
        logger.exception("Failed to exchange code for token")
        return None

def get_drive_service(client_secrets_file, scopes):
    """
    Prefer token stored in environment variable TOKEN_JSON (Render secret).
    TOKEN_JSON must contain the full credentials JSON (what google returns from to_json()).
    """
    token_json = os.environ.get("TOKEN_JSON")
    creds = None
    if token_json:
        try:
            info = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(info, scopes=scopes)
            # refresh if needed
            if not creds.valid:
                request = Request()
                if creds.expired and creds.refresh_token:
                    creds.refresh(request)
        except Exception:
            logger.exception("Failed to load credentials from TOKEN_JSON")
            return None
    else:
        logger.debug("No TOKEN_JSON env var found")
        return None

    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service
    except Exception:
        logger.exception("Failed to build Drive service")
        return None
