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
        self.credentials_file = '/etc/secrets/credentials.json'
        self.token_file = 'token.pickle'
        self.redirect_uri = 'https://tiktok-livestream-recorder.onrender.com/oauth2callback'

    def _load_credentials_config(self):
        """Load credentials from Render secret file"""
        try:
            # First try Render secrets path
            if os.path.exists(self.credentials_file):
                with open(self.credentials_file, 'r') as f:
                    config = json.load(f)
                    logger.info("Loaded credentials from Render secrets")
                    return config
            else:
                # Fallback to environment variable
                creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
                if creds_json:
                    config = json.loads(creds_json)
                    logger.info("Loaded credentials from environment")
                    return config
                
            logger.error("No credentials found in secrets or environment")
            return None
        except Exception as e:
            logger.error(f"Error loading credentials: {str(e)}")
            return None

    def get_authorization_url(self):
        """Get OAuth URL"""
        try:
            creds_config = self._load_credentials_config()
            if not creds_config:
                raise Exception("No credentials configuration found")

            # Force our redirect URI
            if 'web' in creds_config:
                creds_config['web']['redirect_uris'] = [self.redirect_uri]

            flow = InstalledAppFlow.from_client_config(
                creds_config,
                self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            logger.info(f"Generated auth URL with redirect: {self.redirect_uri}")
            return auth_url
            
        except Exception as e:
            logger.error(f"Error generating auth URL: {str(e)}")
            raise

    def handle_callback(self, code):
        """Handle OAuth callback"""
        try:
            creds_config = self._load_credentials_config()
            if not creds_config:
                raise Exception("No credentials configuration found")

            # Force our redirect URI
            if 'web' in creds_config:
                creds_config['web']['redirect_uris'] = [self.redirect_uri]

            flow = InstalledAppFlow.from_client_config(
                creds_config,
                self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            flow.fetch_token(code=code)
            logger.info("Successfully fetched OAuth token")
            return flow.credentials
            
        except Exception as e:
            logger.error(f"Error in callback: {str(e)}")
            return None