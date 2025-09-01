import os
import time
import json
import logging
import requests
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import re
import signal
import sys
from pathlib import Path
import hashlib
import secrets

# Auto-configure Flask app
app = Flask(__name__)

def load_credentials_config():
    """Load configuration from credentials.json"""
    try:
        with open('credentials.json', 'r') as f:
            creds = json.load(f)
        
        # Generate a consistent secret key from client_id
        client_id = creds['web']['client_id']
        secret_key = hashlib.sha256(client_id.encode()).hexdigest()[:32]
        
        return {
            'secret_key': secret_key,
            'client_id': creds['web']['client_id'],
            'client_secret': creds['web']['client_secret'],
            'redirect_uris': creds['web']['redirect_uris']
        }
    except FileNotFoundError:
        logging.error("❌ credentials.json not found! Please add your Google OAuth credentials.")
        # Generate a random secret key as fallback
        return {
            'secret_key': secrets.token_hex(16),
            'client_id': None,
            'client_secret': None,
            'redirect_uris': None
        }
    except Exception as e:
        logging.error(f"❌ Error loading credentials: {e}")
        return {
            'secret_key': secrets.token_hex(16),
            'client_id': None,
            'client_secret': None,
            'redirect_uris': None
        }

# Load configuration
config = load_credentials_config()
app.secret_key = config['secret_key']

# Google Drive API configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CLIENT_SECRETS_FILE = 'credentials.json'

# Global variables
recording_processes = {}
live_status = {}
user_folders = {}
recorder = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tiktok_recorder.log'),
        logging.StreamHandler()
    ]
)

class TikTokRecorder:
    def __init__(self):
        self.users_file = 'usernames.txt'
        self.recordings_dir = 'recordings'
        self.ensure_directories()
        
    def ensure_directories(self):
        """Create necessary directories"""
        os.makedirs(self.recordings_dir, exist_ok=True)
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                f.write('')
                
    def load_users(self):
        """Load users from file"""
        try:
            with open(self.users_file, 'r') as f:
                users = [line.strip() for line in f.readlines() if line.strip()]
            return list(set(users))  # Remove duplicates
        except FileNotFoundError:
            return []
            
    def save_users(self, users):
        """Save users to file"""
        with open(self.users_file, 'w') as f:
            for user in set(users):  # Remove duplicates
                if user.strip():
                    f.write(f"{user.strip()}\n")
                
    def add_user(self, username):
        """Add a new user"""
        users = self.load_users()
        username = username.strip().replace('@', '')
        
        if username and username not in users:
            users.append(username)
            self.save_users(users)
            self.create_user_folder(username)
            logging.info(f"➕ Added user: {username}")
            return True
        return False
        
    def remove_user(self, username):
        """Remove a user"""
        users = self.load_users()
        username = username.strip().replace('@', '')
        
        if username in users:
            users.remove(username)
            self.save_users(users)
            # Stop recording if active
            if username in recording_processes:
                self.stop_recording(username)
            logging.info(f"➖ Removed user: {username}")
            return True
        return False
        
    def create_user_folder(self, username):
        """Create folder structure for a user"""
        user_dir = os.path.join(self.recordings_dir, username)
        os.makedirs(user_dir, exist_ok=True)
        user_folders[username] = user_dir
        logging.info(f"📂 Created folder structure for @{username}")
        
    def check_live_status_improved(self, username):
        """Improved live status detection"""
        try:
            clean_username = username.replace('@', '')
            url = f"https://www.tiktok.com/@{clean_username}/live"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            
            if response.status_code != 200:
                logging.warning(f"❌ HTTP {response.status_code} for @{username}")
                return False
            
            content = response.text.lower()
            
            # Multiple detection methods
            live_indicators = [
                '"live_status":2',
                '"live_status":"2"',
                'islive":true',
                'live_room',
                'live_stream',
                '"status":2',
                'liveroom',
                'live_replay'
            ]
            
            # Check for live indicators
            is_live = any(indicator in content for indicator in live_indicators)
            
            # Additional checks
            if is_live:
                # Verify it's actually a live stream, not just a page with live elements
                not_live_indicators = [
                    'not_live',
                    'offline',
                    'ended',
                    'replay',
                    '"live_status":0',
                    '"live_status":"0"'
                ]
                
                if any(indicator in content for indicator in not_live_indicators):
                    is_live = False
            
            # Log detection details
            if is_live:
                found_indicators = [ind for ind in live_indicators if ind in content]
                logging.info(f"✅ {username} is LIVE! Found: {found_indicators}")
            else:
                logging.info(f"❌ {username} is not live")
                
            return is_live
            
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Error checking {username}: {e}")
            return False
        except Exception as e:
            logging.error(f"❌ Unexpected error for {username}: {e}")
            return False
    
    def get_stream_url(self, username):
        """Get the actual stream URL for recording"""
        try:
            clean_username = username.replace('@', '')
            
            # Use yt-dlp to get stream URL
            cmd = [
                'yt-dlp',
                '--get-url',
                '--no-warnings',
                f'https://www.tiktok.com/@{clean_username}/live'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                stream_url = result.stdout.strip()
                logging.info(f"🔗 Got stream URL for {username}")
                return stream_url
            else:
                logging.error(f"❌ Failed to get stream URL for {username}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logging.error(f"❌ Timeout getting stream URL for {username}")
            return None
        except Exception as e:
            logging.error(f"❌ Error getting stream URL for {username}: {e}")
            return None
    
    def start_recording(self, username):
        """Start recording with FFmpeg"""
        if username in recording_processes:
            logging.info(f"📹 Already recording {username}")
            return False
            
        try:
            # Get stream URL
            stream_url = self.get_stream_url(username)
            if not stream_url:
                logging.error(f"❌ Cannot get stream URL for {username}")
                return False
            
            # Create user folder if it doesn't exist
            self.create_user_folder(username)
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{username}_{timestamp}.mp4"
            filepath = os.path.join(self.recordings_dir, username, filename)
            
            # FFmpeg command with proper error handling
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c', 'copy',  # Copy streams without re-encoding
                '-f', 'mp4',
                '-movflags', '+faststart',
                '-y',  # Overwrite output file
                filepath
            ]
            
            # Start FFmpeg process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            recording_processes[username] = {
                'process': process,
                'filename': filename,
                'filepath': filepath,
                'start_time': datetime.now(),
                'stream_url': stream_url
            }
            
            logging.info(f"🎬 Started recording {username} -> {filename}")
            
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self.monitor_recording,
                args=(username, process),
                daemon=True
            )
            monitor_thread.start()
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Error starting recording for {username}: {e}")
            return False
    
    def monitor_recording(self, username, process):
        """Monitor the recording process"""
        try:
            while process.poll() is None:
                time.sleep(5)
                
                # Check if file is being written to
                if username in recording_processes:
                    filepath = recording_processes[username]['filepath']
                    if os.path.exists(filepath):
                        file_size = os.path.getsize(filepath)
                        duration = datetime.now() - recording_processes[username]['start_time']
                        logging.info(f"📊 {username}: Recording for {duration}, File size: {file_size} bytes")
                    else:
                        logging.warning(f"⚠️ {username}: Recording file not found!")
            
            # Process ended
            return_code = process.returncode
            if return_code == 0:
                logging.info(f"✅ Recording completed for {username}")
            else:
                stderr_output = process.stderr.read() if process.stderr else "No error output"
                logging.error(f"❌ Recording failed for {username} (exit code: {return_code}): {stderr_output}")
            
            # Clean up
            if username in recording_processes:
                filepath = recording_processes[username]['filepath']
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    logging.info(f"💾 Saved recording: {filepath}")
                    # Upload to Google Drive if authorized
                    if 'credentials' in session:
                        self.upload_to_drive(filepath, username)
                else:
                    logging.warning(f"⚠️ Empty or missing recording file: {filepath}")
                
                del recording_processes[username]
                
        except Exception as e:
            logging.error(f"❌ Error monitoring recording for {username}: {e}")
            if username in recording_processes:
                del recording_processes[username]
    
    def stop_recording(self, username):
        """Stop recording for a user"""
        if username in recording_processes:
            try:
                process = recording_processes[username]['process']
                process.terminate()
                
                # Wait for graceful termination
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                
                logging.info(f"🛑 Stopped recording {username}")
                return True
            except Exception as e:
                logging.error(f"❌ Error stopping recording for {username}: {e}")
                return False
        return False
    
    def upload_to_drive(self, filepath, username):
        """Upload recording to Google Drive"""
        try:
            if 'credentials' not in session:
                logging.warning("❌ No Google Drive credentials available")
                return False
                
            creds = Credentials.from_authorized_user_info(session['credentials'])
            service = build('drive', 'v3', credentials=creds)
            
            filename = os.path.basename(filepath)
            
            # Create folder for user if it doesn't exist
            folder_id = self.get_or_create_drive_folder(service, f"TikTok_{username}")
            
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(filepath, resumable=True)
            
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logging.info(f"☁️ Uploaded {filename} to Google Drive (ID: {file.get('id')})")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error uploading to Google Drive: {e}")
            return False
    
    def get_or_create_drive_folder(self, service, folder_name):
        """Get or create a folder in Google Drive"""
        try:
            # Search for existing folder
            results = service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                return folders[0]['id']
            else:
                # Create new folder
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = service.files().create(body=folder_metadata, fields='id').execute()
                return folder.get('id')
                
        except Exception as e:
            logging.error(f"❌ Error with Drive folder: {e}")
            return None

# Initialize recorder
recorder = TikTokRecorder()

@app.route('/')
def index():
    """Main dashboard"""
    users = recorder.load_users()
    
    # Update live status and recording info
    status_info = {}
    for user in users:
        status_info[user] = {
            'live': live_status.get(user, False),
            'recording': user in recording_processes,
            'folder_exists': os.path.exists(os.path.join(recorder.recordings_dir, user))
        }
        
        # Add recording details if active
        if user in recording_processes:
            rec_info = recording_processes[user]
            duration = datetime.now() - rec_info['start_time']
            filepath = rec_info['filepath']
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            
            status_info[user].update({
                'duration': str(duration).split('.')[0],  # Remove microseconds
                'file_size': f"{file_size / 1024 / 1024:.2f} MB" if file_size > 0 else "0 MB",
                'filename': rec_info['filename']
            })
    
    # Check Google Drive authorization
    drive_authorized = 'credentials' in session
    
    return render_template('index.html', 
                         users=users, 
                         status_info=status_info,
                         drive_authorized=drive_authorized,
                         config_loaded=config['client_id'] is not None)

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user"""
    username = request.form.get('username', '').strip()
    
    if username:
        success = recorder.add_user(username)
        if success:
            flash(f"✅ Added user: @{username}", 'success')
        else:
            flash(f"⚠️ User @{username} already exists", 'warning')
    else:
        flash("❌ Please enter a valid username", 'error')
    
    return redirect(url_for('index'))

@app.route('/remove_user', methods=['POST'])
def remove_user():
    """Remove a user"""
    username = request.form.get('username', '').strip()
    
    if username:
        success = recorder.remove_user(username)
        if success:
            flash(f"🗑️ Removed user: @{username}", 'success')
        else:
            flash(f"❌ User @{username} not found", 'error')
    
    return redirect(url_for('index'))

@app.route('/authorize')
def authorize():
    """Start Google OAuth flow"""
    if not config['client_id']:
        flash("❌ Google OAuth not configured. Please add credentials.json", 'error')
        return redirect(url_for('index'))
    
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=url_for('oauth_callback', _external=True)
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        return redirect(authorization_url)
        
    except Exception as e:
        logging.error(f"❌ OAuth error: {e}")
        flash(f"❌ OAuth setup error: {e}", 'error')
        return redirect(url_for('index'))

@app.route('/oauth_callback')
def oauth_callback():
    """Handle OAuth callback"""
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=url_for('oauth_callback', _external=True)
        )
        
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        flash("✅ Google Drive authorized successfully!", 'success')
        logging.info("✅ Google Drive authorization completed")
        
    except Exception as e:
        logging.error(f"❌ OAuth callback error: {e}")
        flash(f"❌ Authorization failed: {e}", 'error')
    
    return redirect(url_for('index'))

@app.route('/revoke')
def revoke():
    """Revoke Google Drive authorization"""
    if 'credentials' in session:
        del session['credentials']
        flash("🔓 Google Drive authorization revoked", 'info')
    return redirect(url_for('index'))

@app.route('/status')
def status():
    """Get current status as JSON"""
    users = recorder.load_users()
    status_data = {
        'users': [],
        'drive_authorized': 'credentials' in session,
        'total_users': len(users),
        'live_users': sum(1 for user in users if live_status.get(user, False)),
        'recording_users': len(recording_processes)
    }
    
    for user in users:
        user_info = {
            'username': user,
            'live': live_status.get(user, False),
            'recording': user in recording_processes,
            'folder_exists': os.path.exists(os.path.join(recorder.recordings_dir, user))
        }
        
        if user in recording_processes:
            rec_info = recording_processes[user]
            duration = datetime.now() - rec_info['start_time']
            filepath = rec_info['filepath']
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            
            user_info.update({
                'duration': str(duration).split('.')[0],
                'file_size_mb': round(file_size / 1024 / 1024, 2),
                'filename': rec_info['filename']
            })
        
        status_data['users'].append(user_info)
    
    return jsonify(status_data)

def check_all_users():
    """Check all users for live status and start/stop recordings"""
    users = recorder.load_users()
    logging.info(f"🔍 Checking {len(users)} users...")
    
    for user in users:
        try:
            logging.info(f"🔍 Checking live status for @{user}")
            is_live = recorder.check_live_status_improved(user)
            live_status[user] = is_live
            
            if is_live:
                logging.info(f"🔴 {user} is LIVE!")
                if user not in recording_processes:
                    logging.info(f"🎬 Starting recording for {user}")
                    success = recorder.start_recording(user)
                    if success:
                        logging.info(f"✅ Recording started for {user}")
                    else:
                        logging.error(f"❌ Failed to start recording for {user}")
                else:
                    # Check if recording is still active
                    process = recording_processes[user]['process']
                    if process.poll() is not None:
                        logging.warning(f"⚠️ Recording process died for {user}, restarting...")
                        del recording_processes[user]
                        recorder.start_recording(user)
                    else:
                        logging.info(f"📹 Continue recording {user}")
            else:
                logging.info(f"❌ {user} is not live")
                if user in recording_processes:
                    logging.info(f"🛑 Stopping recording for {user}")
                    recorder.stop_recording(user)
            
            # Small delay between checks
            time.sleep(2)
            
        except Exception as e:
            logging.error(f"❌ Error checking {user}: {e}")
            live_status[user] = False

def monitoring_loop():
    """Main monitoring loop"""
    logging.info("🔄 Auto-monitoring started")
    
    while True:
        try:
            check_all_users()
            logging.info("⏱️ Waiting 30s before next cycle...")
            time.sleep(30)
        except KeyboardInterrupt:
            logging.info("⏹️ Monitoring stopped by user")
            break
        except Exception as e:
            logging.error(f"❌ Error in monitoring loop: {e}")
            time.sleep(10)  # Wait a bit before retrying

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logging.info("🛑 Shutdown signal received")
    
    # Stop all recordings
    for username in list(recording_processes.keys()):
        recorder.stop_recording(username)
    
    sys.exit(0)

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TikTok Live Recorder - Final Version</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            padding: 30px;
            backdrop-filter: blur(10px);
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .header h1 {
            color: #333;
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .status-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .status-card {
            background: linear-gradient(45deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
            transform: translateY(0);
            transition: transform 0.3s ease;
        }
        
        .status-card:hover {
            transform: translateY(-5px);
        }
        
        .status-card.drive {
            background: linear-gradient(45deg, #4285f4, #34a853);
        }
        
        .status-card.config {
            background: linear-gradient(45deg, #9c88ff, #8c7ae6);
        }
        
        .status-card.recording {
            background: linear-gradient(45deg, #ff9ff3, #f368e0);
        }
        
        .control-section {
            background: rgba(255, 255, 255, 0.8);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.05);
        }
        
        .control-section h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 1.5rem;
        }
        
        .form-group {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        
        .form-group input {
            flex: 1;
            min-width: 200px;
            padding: 12px 15px;
            border: 2px solid #e1e8ed;
            border-radius: 25px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }
        
        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #ff6b6b, #ee5a24);
            color: white;
        }
        
        .btn-success {
            background: linear-gradient(45deg, #2ed573, #1e90ff);
            color: white;
        }
        
        .users-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .user-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
            border-left: 5px solid #ddd;
            transition: all 0.3s ease;
        }
        
        .user-card.live {
            border-left-color: #ff6b6b;
            animation: pulse 2s infinite;
        }
        
        .user-card.recording {
            border-left-color: #2ed573;
            background: linear-gradient(135deg, #f8fff8 0%, #e8f5e8 100%);
        }
        
        @keyframes pulse {
            0% { box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1); }
            50% { box-shadow: 0 10px 30px rgba(255, 107, 107, 0.3); }
            100% { box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1); }
        }
        
        .user-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .username {
            font-size: 1.2rem;
            font-weight: 600;
            color: #333;
        }
        
        .status-badge {
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .status-badge.live {
            background: #ff6b6b;
            color: white;
        }
        
        .status-badge.offline {
            background: #95a5a6;
            color: white;
        }
        
        .status-badge.recording {
            background: #2ed573;
            color: white;
            animation: blink 1s infinite;
        }
        
        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0.7; }
        }
        
        .user-info {
            margin-top: 10px;
            font-size: 0.9rem;
            color: #666;
        }
        
        .user-info .info-item {
            margin-bottom: 5px;
        }
        
        .recording-details {
            background: rgba(46, 213, 115, 0.1);
            border-radius: 10px;
            padding: 10px;
            margin-top: 10px;
            border: 1px solid rgba(46, 213, 115, 0.3);
        }
        
        .remove-btn {
            background: #e74c3c;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        
        .remove-btn:hover {
            background: #c0392b;
        }
        
        .flash-messages {
            margin-bottom: 20px;
        }
        
        .flash-message {
            padding: 12px 20px;
            border-radius: 10px;
            margin-bottom: 10px;
            font-weight: 500;
        }
        
        .flash-message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .flash-message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .flash-message.warning {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        
        .flash-message.info {
            background: #cce7ff;
            color: #004085;
            border: 1px solid #99d6ff;
        }
        
        .auto-refresh {
            text-align: center;
            margin-top: 20px;
            color: #666;
            font-size: 0.9rem;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
                margin: 10px;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .status-cards {
                grid-template-columns: 1fr;
            }
            
            .form-group {
                flex-direction: column;
            }
            
            .form-group input {
                min-width: auto;
            }
        }
    </style>
    <script>
        // Auto-refresh every 10 seconds
        setInterval(function() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    updateStatus(data);
                })
                .catch(error => {
                    console.error('Error fetching status:', error);
                });
        }, 10000);
        
        function updateStatus(data) {
            // Update status cards
            document.getElementById('total-users').textContent = data.total_users;
            document.getElementById('live-users').textContent = data.live_users;
            document.getElementById('recording-users').textContent = data.recording_users;
            
            // Update drive status
            const driveStatus = document.getElementById('drive-status');
            if (data.drive_authorized) {
                driveStatus.textContent = 'Authorized ✅';
                driveStatus.style.color = '#2ed573';
            } else {
                driveStatus.textContent = 'Not Authorized ❌';
                driveStatus.style.color = '#ff6b6b';
            }
            
            // Update last check time
            document.getElementById('last-check').textContent = new Date().toLocaleTimeString();
        }
        
        function confirmRemove(username) {
            return confirm(`Are you sure you want to remove @${username}?`);
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 TikTok Live Recorder</h1>
            <p>Autonomous live stream monitoring and recording system</p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-message {{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        
        <div class="status-cards">
            <div class="status-card">
                <h3>👥 Total Users</h3>
                <h2 id="total-users">{{ users|length }}</h2>
            </div>
            <div class="status-card recording">
                <h3>🔴 Live Users</h3>
                <h2 id="live-users">{{ status_info.values() | selectattr('live') | list | length }}</h2>
            </div>
            <div class="status-card drive">
                <h3>📹 Recording</h3>
                <h2 id="recording-users">{{ status_info.values() | selectattr('recording') | list | length }}</h2>
            </div>
            <div class="status-card config">
                <h3>☁️ Google Drive</h3>
                <p id="drive-status">
                    {% if drive_authorized %}
                        Authorized ✅
                    {% else %}
                        Not Authorized ❌
                    {% endif %}
                </p>
            </div>
        </div>
        
        {% if not config_loaded %}
        <div class="control-section" style="background: #ffe6e6; border: 2px solid #ff6b6b;">
            <h2>⚠️ Configuration Required</h2>
            <p>Please add your <strong>credentials.json</strong> file to enable Google OAuth and full functionality.</p>
        </div>
        {% endif %}
        
        <div class="control-section">
            <h2>👤 User Management</h2>
            <form method="POST" action="/add_user">
                <div class="form-group">
                    <input type="text" name="username" placeholder="Enter TikTok username (e.g., @username)" required>
                    <button type="submit" class="btn btn-primary">➕ Add User</button>
                </div>
            </form>
            
            {% if not drive_authorized and config_loaded %}
            <div style="margin-top: 20px;">
                <a href="/authorize" class="btn btn-success">🔐 Authorize Google Drive</a>
            </div>
            {% elif drive_authorized %}
            <div style="margin-top: 20px;">
                <a href="/revoke" class="btn btn-danger">🔓 Revoke Google Drive Access</a>
            </div>
            {% endif %}
        </div>
        
        <div class="control-section">
            <h2>📊 User Status</h2>
            {% if users %}
                <div class="users-grid">
                    {% for user in users %}
                    <div class="user-card {% if status_info[user].live %}live{% endif %} {% if status_info[user].recording %}recording{% endif %}">
                        <div class="user-header">
                            <span class="username">@{{ user }}</span>
                            <div>
                                {% if status_info[user].live %}
                                    <span class="status-badge live">🔴 LIVE</span>
                                {% else %}
                                    <span class="status-badge offline">⚪ OFFLINE</span>
                                {% endif %}
                                
                                {% if status_info[user].recording %}
                                    <span class="status-badge recording">🎬 REC</span>
                                {% endif %}
                            </div>
                        </div>
                        
                        <div class="user-info">
                            <div class="info-item">
                                📁 Folder: {% if status_info[user].folder_exists %}✅ Created{% else %}❌ Missing{% endif %}
                            </div>
                            
                            {% if status_info[user].recording %}
                            <div class="recording-details">
                                <div class="info-item"><strong>📹 Recording Active</strong></div>
                                <div class="info-item">⏱️ Duration: {{ status_info[user].duration }}</div>
                                <div class="info-item">💾 Size: {{ status_info[user].file_size }}</div>
                                <div class="info-item">📄 File: {{ status_info[user].filename }}</div>
                            </div>
                            {% endif %}
                        </div>
                        
                        <form method="POST" action="/remove_user" style="margin-top: 15px;" onsubmit="return confirmRemove('{{ user }}')">
                            <input type="hidden" name="username" value="{{ user }}">
                            <button type="submit" class="remove-btn">🗑️ Remove</button>
                        </form>
                    </div>
                    {% endfor %}
                </div>
            {% else %}
                <div style="text-align: center; padding: 40px; color: #666;">
                    <h3>No users added yet</h3>
                    <p>Add some TikTok usernames to start monitoring live streams!</p>
                </div>
            {% endif %}
        </div>
        
        <div class="auto-refresh">
            🔄 Auto-refreshing every 10 seconds | Last check: <span id="last-check">{{ moment().format('HH:mm:ss') }}</span>
        </div>
    </div>
</body>
</html>
'''

# Save template
os.makedirs('templates', exist_ok=True)
with open('templates/index.html', 'w') as f:
    f.write(HTML_TEMPLATE)

if __name__ == '__main__':
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create initial folder structures for existing users
    users = recorder.load_users()
    if users:
        logging.info(f"📁 Creating folder structure for {len(users)} users...")
        for user in users:
            recorder.create_user_folder(user)
        logging.info("✅ All folder structures created successfully")
    
    # Start monitoring in a separate thread
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    logging.info("🔄 Auto-commit scheduler started")
    
    # Get port from environment (for Render deployment)
    port = int(os.environ.get('PORT', 5000))
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
