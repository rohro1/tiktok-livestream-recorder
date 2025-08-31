"""
Google Drive OAuth Helper
Handles Google OAuth2 flow for Drive API access
"""

import os
import json
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

logger = logging.getLogger(__name__)

class DriveOAuth:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        """
        Initialize OAuth helper
        
        Args:
            credentials_file (str): Path to OAuth2 credentials JSON
            token_file (str): Path to store access tokens
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.scopes = ['https://www.googleapis.com/auth/drive.file']
        
        # For Render deployment
        self.redirect_uri = os.environ.get('OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/callback')

    def load_credentials(self):
        """
        Load existing credentials from token file
        
        Returns:
            Credentials object if valid, None otherwise
        """
        try:
            if os.path.exists(self.token_file):
                creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
                
                # Refresh if expired
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        self._save_credentials(creds)
                        logger.info("Refreshed expired credentials")
                    except Exception as e:
                        logger.error(f"Error refreshing credentials: {e}")
                        return None
                
                if creds and creds.valid:
                    logger.info("Loaded valid credentials")
                    return creds
                    
            logger.info("No valid credentials found")
            return None
            
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            return None

    def _load_credentials_config(self):
        """Load credentials from file or environment"""
        if os.environ.get('GOOGLE_CREDENTIALS_JSON'):
            try:
                return json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
            except Exception as e:
                logger.error(f"Failed to parse credentials from environment: {e}")
                return None
        
        try:
            with open(self.credentials_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load credentials file: {e}")
            return None

    def get_authorization_url(self):
        """Get OAuth URL with correct redirect"""
        creds_config = self._load_credentials_config()
        if not creds_config:
            raise Exception("No credentials configuration found")

        # Use environment redirect URI if available, fallback to credentials
        redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
        if redirect_uri:
            creds_config['web']['redirect_uris'] = [redirect_uri]
            creds_config['web']['redirect_uri'] = redirect_uri

        flow = InstalledAppFlow.from_client_config(
            creds_config, 
            self.scopes,
            redirect_uri=redirect_uri
        )
        return flow.authorization_url(prompt='consent')[0]

    def handle_callback(self, authorization_code):
        """
        Handle OAuth callback and exchange code for credentials
        
        Args:
            authorization_code (str): Authorization code from callback
        
        Returns:
            Credentials object if successful, None otherwise
        """
        try:
            # Restore flow state
            flow = self._load_flow_state()
            if not flow:
                logger.error("No flow state found")
                return None

            # Exchange code for credentials
            flow.fetch_token(code=authorization_code)
            creds = flow.credentials

            # Save credentials
            self._save_credentials(creds)
            
            logger.info("OAuth callback successful, credentials saved")
            return creds
            
        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}")
            return None

    def _save_credentials(self, credentials):
        """Save credentials to file"""
        try:
            with open(self.token_file, 'w') as f:
                f.write(credentials.to_json())
            logger.debug("Credentials saved")
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")

    def _save_flow_state(self, flow):
        """Save OAuth flow state for callback"""
        try:
            flow_state = {
                'client_config': flow.client_config,
                'redirect_uri': flow.redirect_uri,
                'scopes': flow.scopes
            }
            
            with open('flow_state.json', 'w') as f:
                json.dump(flow_state, f)
                
        except Exception as e:
            logger.error(f"Error saving flow state: {e}")

    def _load_flow_state(self):
        """Load OAuth flow state from file"""
        try:
            if not os.path.exists('flow_state.json'):
                return None
                
            with open('flow_state.json', 'r') as f:
                flow_state = json.load(f)
            
            # Recreate flow
            flow = Flow.from_client_config(
                flow_state['client_config'],
                scopes=flow_state['scopes'],
                redirect_uri=flow_state['redirect_uri']
            )
            
            return flow
            
        except Exception as e:
            logger.error(f"Error loading flow state: {e}")
            return None

    def revoke_credentials(self):
        """Revoke stored credentials"""
        try:
            creds = self.load_credentials()
            if creds:
                # Revoke the credentials
                revoke_url = f'https://oauth2.googleapis.com/revoke?token={creds.token}'
                import requests
                response = requests.post(revoke_url)
                
                if response.status_code == 200:
                    logger.info("Credentials revoked successfully")
                else:
                    logger.warning(f"Revoke response: {response.status_code}")

            # Remove local files
            for file_path in [self.token_file, 'flow_state.json']:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            logger.info("Local credential files removed")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking credentials: {e}")
            return False

    def test_connection(self):
        """
        Test Google Drive API connection
        
        Returns:
            bool: True if connection works, False otherwise
        """
        try:
            creds = self.load_credentials()
            if not creds:
                return False

            service = build('drive', 'v3', credentials=creds)
            
            # Try to get user info
            about = service.about().get(fields='user').execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            
            logger.info(f"Drive API connection successful for: {user_email}")
            return True
            
        except Exception as e:
            logger.error(f"Drive API connection test failed: {e}")
            return False