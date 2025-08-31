"""
Google Drive OAuth Helper
Handles Google OAuth2 flow for Drive API access
"""

import os
import json
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class DriveOAuth:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/drive.file']

    def _load_credentials_config(self):
        """Load credentials from Render secret file"""
        try:
            if os.path.exists('/etc/secrets/credentials.json'):
                with open('/etc/secrets/credentials.json', 'r') as f:
                    return json.load(f)
            raise FileNotFoundError("No credentials.json found")
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def get_authorization_url(self):
        """Get OAuth URL"""
        try:
            creds_config = self._load_credentials_config()
            if not creds_config:
                raise Exception("No credentials configuration found")

            # Use configured redirect URI from credentials
            flow = InstalledAppFlow.from_client_config(
                creds_config,
                self.scopes
            )
            
            # Use the first configured redirect URI
            if 'web' in creds_config and 'redirect_uris' in creds_config['web']:
                flow.redirect_uri = creds_config['web']['redirect_uris'][0]
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            return auth_url
            
        except Exception as e:
            logger.error(f"Failed to get auth URL: {e}")
            raise

    def handle_callback(self, code):
        """Handle OAuth callback"""
        try:
            creds_config = self._load_credentials_config()
            if not creds_config:
                raise Exception("No credentials configuration found")

            flow = InstalledAppFlow.from_client_config(
                creds_config,
                self.scopes
            )
            
            # Use the same redirect URI as authorization
            if 'web' in creds_config and 'redirect_uris' in creds_config['web']:
                flow.redirect_uri = creds_config['web']['redirect_uris'][0]
            
            flow.fetch_token(code=code)
            return flow.credentials
            
        except Exception as e:
            logger.error(f"Failed to handle callback: {e}")
            return None