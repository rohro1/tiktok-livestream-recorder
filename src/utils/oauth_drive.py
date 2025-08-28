# src/utils/oauth_drive.py

import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Path to your OAuth client secret JSON
CLIENT_SECRETS_FILE = "credentials.json"
# Path to store user's credentials after authorization
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# -------------------------
# OAuth Flow
# -------------------------
def get_flow():
    """Create a Flow object for Google OAuth."""
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ.get("OAUTH_REDIRECT_URI")  # must match your Render env var
    )

# -------------------------
# Save / Load Credentials
# -------------------------
def save_credentials(credentials):
    """Save Google credentials to TOKEN_FILE."""
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(credentials, f)

def load_credentials():
    """Load Google credentials from TOKEN_FILE."""
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)
    return creds

# -------------------------
# Google Drive Service
# -------------------------
def get_drive_service():
    """Return a Google Drive service object."""
    creds = load_credentials()
    if not creds:
        raise Exception("Google Drive credentials not found. Please authorize first.")
    return build("drive", "v3", credentials=creds)
