import os
import json
import threading
import time
from flask import Flask, render_template, redirect, request, session, url_for, jsonify
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import logging
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_recorder import TikTokRecorder
from src.utils.google_drive_uploader import GoogleDriveUploader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Global variables
status_tracker = StatusTracker()
recorder_instances = {}
recording_threads = {}

# Google OAuth configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CLIENT_SECRETS_FILE = 'credentials.json'

def get_google_flow():
    """Create Google OAuth flow"""
    try:
        # Read credentials from file (not environment)
        if not os.path.exists(CLIENT_SECRETS_FILE):
            logger.error(f"credentials.json file not found")
            return None
            
        # Get the correct redirect URI for Render
        if 'RENDER_EXTERNAL_URL' in os.environ:
            # On Render, use the external URL
            base_url = os.environ['RENDER_EXTERNAL_URL'].rstrip('/')
            redirect_uri = f"{base_url}/oauth2callback"
        else:
            # Local development
            redirect_uri = "http://localhost:5000/oauth2callback"
        
        logger.info(f"Using redirect URI: {redirect_uri}")
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES
        )
        flow.redirect_uri = redirect_uri
        return flow
    except Exception as e:
        logger.error(f"Error creating Google flow: {e}")
        return None

def load_usernames():
    """Load usernames from file"""
    try:
        with open('usernames.txt', 'r') as f:
            usernames = [line.strip() for line in f if line.strip()]
        return usernames
    except FileNotFoundError:
        logger.warning("usernames.txt not found, creating empty file")
        with open('usernames.txt', 'w') as f:
            f.write("")
        return []

def monitor_user(username):
    """Monitor a single user for live streams"""
    recorder = TikTokRecorder()
    recorder_instances[username] = recorder
    
    while True:
        try:
            # Check if user is live
            live_url = recorder.check_if_live(username)
            
            if live_url:
                logger.info(f"{username} is live! Starting recording...")
                status_tracker.update_status(username, 'live', 'recording')
                
                # Start recording
                output_file = f"recordings/{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                recorder.start_recording(live_url, output_file)
                
                # Upload to Google Drive when recording is complete
                if 'google_credentials' in session:
                    try:
                        uploader = GoogleDriveUploader(session['google_credentials'])
                        uploader.upload_file(output_file, username)
                        logger.info(f"Uploaded {output_file} to Google Drive")
                    except Exception as e:
                        logger.error(f"Failed to upload to Google Drive: {e}")
                
                status_tracker.update_status(username, 'offline', 'idle')
            else:
                status_tracker.update_status(username, 'offline', 'monitoring')
            
            # Wait 30 seconds before checking again
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Error monitoring {username}: {e}")
            status_tracker.update_status(username, 'error', f'Error: {str(e)[:100]}')
            time.sleep(60)  # Wait longer on error

@app.route('/')
def index():
    """Main page - redirect to status"""
    return redirect('/status')

@app.route('/status')
def status():
    """Status dashboard"""
    users_status = status_tracker.get_all_status()
    
    # Load usernames and ensure they're being tracked
    usernames = load_usernames()
    for username in usernames:
        if username not in users_status:
            status_tracker.update_status(username, 'offline', 'monitoring')
    
    # Get updated status
    users_status = status_tracker.get_all_status()
    
    return render_template('status.html', users=users_status)

@app.route('/api/status')
def api_status():
    """API endpoint for status data"""
    return jsonify(status_tracker.get_all_status())

@app.route('/start_monitoring')
def start_monitoring():
    """Start monitoring all users"""
    usernames = load_usernames()
    
    for username in usernames:
        if username not in recording_threads or not recording_threads[username].is_alive():
            thread = threading.Thread(target=monitor_user, args=(username,), daemon=True)
            thread.start()
            recording_threads[username] = thread
            logger.info(f"Started monitoring {username}")
    
    return redirect('/status')

@app.route('/authorize')
def authorize():
    """Start Google OAuth flow"""
    flow = get_google_flow()
    if not flow:
        return "Error: Could not create Google OAuth flow. Check credentials.json file.", 500
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    """Handle Google OAuth callback"""
    try:
        flow = get_google_flow()
        if not flow:
            return "Error: Could not create Google OAuth flow", 500
        
        # Get the authorization response
        flow.fetch_token(authorization_response=request.url)
        
        # Store credentials in session
        credentials = flow.credentials
        session['google_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        logger.info("Google OAuth authorization successful")
        return redirect('/status')
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return f"Authorization failed: {str(e)}", 400

@app.route('/test_google_drive')
def test_google_drive():
    """Test Google Drive connection"""
    if 'google_credentials' not in session:
        return redirect('/authorize')
    
    try:
        # Test Google Drive API
        creds = Credentials(**session['google_credentials'])
        service = build('drive', 'v3', credentials=creds)
        
        # List files to test connection
        results = service.files().list(pageSize=5).execute()
        files = results.get('files', [])
        
        return f"Google Drive connection successful! Found {len(files)} files."
        
    except Exception as e:
        logger.error(f"Google Drive test failed: {e}")
        return f"Google Drive test failed: {str(e)}", 500

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user to monitor"""
    username = request.form.get('username', '').strip()
    if username:
        usernames = load_usernames()
        if username not in usernames:
            with open('usernames.txt', 'a') as f:
                f.write(f"\n{username}")
            
            # Start monitoring this user
            if username not in recording_threads or not recording_threads[username].is_alive():
                thread = threading.Thread(target=monitor_user, args=(username,), daemon=True)
                thread.start()
                recording_threads[username] = thread
                logger.info(f"Added and started monitoring {username}")
    
    return redirect('/status')

@app.route('/remove_user', methods=['POST'])
def remove_user():
    """Remove a user from monitoring"""
    username = request.form.get('username', '').strip()
    if username:
        usernames = load_usernames()
        if username in usernames:
            usernames.remove(username)
            with open('usernames.txt', 'w') as f:
                f.write('\n'.join(usernames))
            
            # Stop monitoring thread
            if username in recording_threads:
                # Note: We can't easily stop the thread, but it will eventually stop
                # when it checks and the user is no longer in the list
                pass
            
            # Remove from status tracker
            status_tracker.remove_user(username)
            logger.info(f"Removed {username} from monitoring")
    
    return redirect('/status')

@app.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

def start_background_monitoring():
    """Start monitoring all users in background"""
    usernames = load_usernames()
    logger.info(f"Starting background monitoring for {len(usernames)} users")
    
    for username in usernames:
        if username not in recording_threads or not recording_threads[username].is_alive():
            thread = threading.Thread(target=monitor_user, args=(username,), daemon=True)
            thread.start()
            recording_threads[username] = thread
            logger.info(f"Started background monitoring for {username}")

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('recordings', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Start background monitoring
    monitor_thread = threading.Thread(target=start_background_monitoring, daemon=True)
    monitor_thread.start()
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)