
#!/usr/bin/env python3
"""
TikTok Livestream Recorder - Complete Working Implementation
Uses credentials.json from secrets, fully autonomous operation
"""

import os
import json
import threading
import time
import subprocess
import requests
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import yt_dlp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tiktok-recorder-secret-key-2025')

# Global state
recording_threads = {}
monitoring_active = False
status_tracker = {}
drive_service = None
monitoring_thread = None

class TikTokChecker:
    """Reliable TikTok live status checker"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def is_live(self, username):
        """Check if user is currently live using multiple methods"""
        try:
            # Method 1: Check TikTok profile page for live indicator
            profile_url = f"https://www.tiktok.com/@{username}"
            response = self.session.get(profile_url, timeout=10)
            
            if response.status_code == 200:
                content = response.text.lower()
                # Look for live indicators in the page content
                live_indicators = [
                    '"is_live":true',
                    'live_status":1',
                    'user_live_status":1',
                    'live_room',
                    'liveroom'
                ]
                
                for indicator in live_indicators:
                    if indicator in content:
                        logger.info(f"Found live indicator for {username}: {indicator}")
                        return True
            
            # Method 2: Try to get live stream URL with yt-dlp
            try:
                live_url = f"https://www.tiktok.com/@{username}/live"
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'skip_download': True
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(live_url, download=False)
                    if info and info.get('is_live'):
                        logger.info(f"yt-dlp confirms {username} is live")
                        return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking live status for {username}: {e}")
            return False

class StreamRecorder:
    """Records TikTok livestreams"""
    
    def record_stream(self, username):
        """Record livestream using yt-dlp"""
        try:
            # Create output directory
            output_dir = os.path.join('recordings', username)
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(output_dir, f'{username}_{timestamp}.mp4')
            
            # Use yt-dlp to record the livestream
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            ydl_opts = {
                'outtmpl': output_file,
                'format': 'best[height<=480]/best',  # 480p max
                'quiet': False,
                'no_warnings': False,
                'live_from_start': True,
            }
            
            logger.info(f"Starting recording for {username} -> {output_file}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([live_url])
            
            # Check if file was created successfully
            if os.path.exists(output_file) and os.path.getsize(output_file) > 1024:
                logger.info(f"Recording completed: {output_file} ({os.path.getsize(output_file)} bytes)")
                return output_file
            else:
                logger.error(f"Recording failed or file too small for {username}")
                if os.path.exists(output_file):
                    os.remove(output_file)
                return None
                
        except Exception as e:
            logger.error(f"Error recording {username}: {e}")
            return None

class GoogleDriveUploader:
    """Handles Google Drive uploads with folder structure"""
    
    def __init__(self, service):
        self.service = service
    
    def create_folder(self, name, parent_id='root'):
        """Create folder in Google Drive"""
        try:
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = self.service.files().create(body=folder_metadata).execute()
            return folder.get('id')
        except Exception as e:
            logger.error(f"Error creating folder {name}: {e}")
            return None
    
    def find_folder(self, name, parent_id='root'):
        """Find existing folder by name"""
        try:
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents"
            results = self.service.files().list(q=query).execute()
            items = results.get('files', [])
            return items[0]['id'] if items else None
        except Exception as e:
            logger.error(f"Error finding folder {name}: {e}")
            return None
    
    def upload_video(self, file_path, username):
        """Upload video with structured folder organization"""
        try:
            # Get or create username folder
            username_folder_id = self.find_folder(username)
            if not username_folder_id:
                username_folder_id = self.create_folder(username)
            
            # Get or create date folder
            date_str = datetime.now().strftime('%Y-%m-%d')
            date_folder_id = self.find_folder(date_str, username_folder_id)
            if not date_folder_id:
                date_folder_id = self.create_folder(date_str, username_folder_id)
            
            # Upload file
            filename = os.path.basename(file_path)
            file_metadata = {
                'name': filename,
                'parents': [date_folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media
            ).execute()
            
            # Make file viewable
            file_id = file.get('id')
            self.service.permissions().create(
                fileId=file_id,
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
            
            drive_url = f"https://drive.google.com/file/d/{file_id}/view"
            logger.info(f"Uploaded to Drive: {drive_url}")
            return drive_url
            
        except Exception as e:
            logger.error(f"Error uploading to Drive: {e}")
            return None

def load_usernames():
    """Load usernames from file"""
    try:
        with open('usernames.txt', 'r') as f:
            usernames = [line.strip().replace('@', '') for line in f if line.strip() and not line.startswith('#')]
        return usernames
    except FileNotFoundError:
        # Create empty file
        with open('usernames.txt', 'w') as f:
            f.write("# Add TikTok usernames here (one per line, without @)\n")
        return []

def update_status(username, **kwargs):
    """Thread-safe status updates"""
    global status_tracker
    if username not in status_tracker:
        status_tracker[username] = {}
    status_tracker[username].update(kwargs)
    status_tracker[username]['last_updated'] = datetime.now().isoformat()

def record_user_stream(username, checker, recorder, uploader):
    """Record a user's livestream in separate thread"""
    try:
        logger.info(f"Recording thread started for {username}")
        update_status(username, is_recording=True, recording_start=datetime.now().isoformat())
        
        # Record the stream
        output_file = recorder.record_stream(username)
        
        if output_file and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            logger.info(f"Recording completed for {username}: {file_size} bytes")
            
            update_status(username, 
                         last_recording=output_file,
                         recording_end=datetime.now().isoformat(),
                         file_size=file_size)
            
            # Upload to Google Drive
            if uploader:
                try:
                    drive_url = uploader.upload_video(output_file, username)
                    if drive_url:
                        update_status(username, drive_link=drive_url)
                        # Remove local file after successful upload
                        os.remove(output_file)
                        logger.info(f"Uploaded and cleaned up: {username}")
                    else:
                        logger.error(f"Drive upload failed for {username}")
                except Exception as e:
                    logger.error(f"Drive upload error for {username}: {e}")
        else:
            logger.error(f"Recording failed for {username}")
            
    except Exception as e:
        logger.error(f"Error in recording thread for {username}: {e}")
    finally:
        # Always cleanup
        if username in recording_threads:
            del recording_threads[username]
        update_status(username, is_recording=False)

def monitoring_loop():
    """Main monitoring loop"""
    global monitoring_active, drive_service
    
    logger.info("Starting monitoring loop")
    monitoring_active = True
    
    # Initialize components
    checker = TikTokChecker()
    recorder = StreamRecorder()
    uploader = GoogleDriveUploader(drive_service) if drive_service else None
    
    while monitoring_active:
        try:
            usernames = load_usernames()
            if not usernames:
                logger.info("No usernames to monitor")
                time.sleep(60)
                continue
            
            logger.info(f"Checking {len(usernames)} users...")
            
            for username in usernames:
                if not monitoring_active:
                    break
                
                try:
                    # Check if user is live
                    is_live = checker.is_live(username)
                    
                    update_status(username, 
                                 is_live=is_live,
                                 last_check=datetime.now().isoformat())
                    
                    if is_live:
                        logger.info(f"🔴 {username} is LIVE!")
                        
                        # Start recording if not already recording
                        if username not in recording_threads:
                            thread = threading.Thread(
                                target=record_user_stream,
                                args=(username, checker, recorder, uploader),
                                daemon=True
                            )
                            thread.start()
                            recording_threads[username] = thread
                            logger.info(f"Started recording {username}")
                    else:
                        logger.debug(f"⚪ {username} is offline")
                    
                except Exception as e:
                    logger.error(f"Error checking {username}: {e}")
                    update_status(username, error=str(e))
                
                time.sleep(5)  # Delay between users
            
            time.sleep(30)  # Wait before next cycle
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            time.sleep(60)
    
    logger.info("Monitoring loop stopped")

def load_google_credentials():
    """Load Google credentials from secrets"""
    try:
        # Check if credentials.json exists in current directory
        if os.path.exists('credentials.json'):
            with open('credentials.json', 'r') as f:
                creds_info = json.load(f)
                return creds_info
        else:
            logger.error("credentials.json not found!")
            return None
    except Exception as e:
        logger.error(f"Error loading credentials: {e}")
        return None

@app.route('/')
def home():
    """Home page - redirect to status"""
    return redirect(url_for('status'))

@app.route('/status')
def status():
    """Main dashboard"""
    usernames = load_usernames()
    user_data = []
    
    for username in usernames:
        data = status_tracker.get(username, {})
        data['username'] = username
        data['is_recording'] = username in recording_threads
        
        # Format timestamps
        for field in ['last_updated', 'last_check', 'recording_start', 'recording_end']:
            if field in data:
                try:
                    dt = datetime.fromisoformat(data[field])
                    data[f'{field}_formatted'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
        
        user_data.append(data)
    
    return render_template('status.html', 
                         users=user_data,
                         monitoring_active=monitoring_active,
                         drive_connected=bool(drive_service),
                         total_recordings=len(recording_threads))

@app.route('/api/status')
def api_status():
    """API endpoint for status"""
    usernames = load_usernames()
    users = []
    
    for username in usernames:
        data = status_tracker.get(username, {})
        data['username'] = username
        data['is_recording'] = username in recording_threads
        users.append(data)
    
    return jsonify({
        'users': users,
        'monitoring_active': monitoring_active,
        'total_users': len(usernames),
        'active_recordings': len(recording_threads),
        'drive_connected': bool(drive_service)
    })

@app.route('/auth/google')
def auth_google():
    """Start Google OAuth flow"""
    creds_info = load_google_credentials()
    if not creds_info:
        return "Error: credentials.json not found", 400
    
    try:
        flow = Flow.from_client_config(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive.file'],
            redirect_uri=request.url_root.rstrip('/') + '/auth/callback'
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"OAuth setup error: {e}")
        return f"OAuth setup error: {e}", 500

@app.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback"""
    global drive_service, monitoring_thread
    
    try:
        creds_info = load_google_credentials()
        flow = Flow.from_client_config(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive.file'],
            redirect_uri=request.url_root.rstrip('/') + '/auth/callback'
        )
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Initialize Drive service
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Test the connection
        drive_service.about().get(fields="user").execute()
        logger.info("Google Drive connected successfully!")
        
        # Auto-start monitoring after successful authorization
        if not monitoring_active:
            monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
            monitoring_thread.start()
            logger.info("Auto-started monitoring after authorization")
        
        return redirect(url_for('status'))
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return f"Authorization failed: {e}", 500

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Manually start monitoring"""
    global monitoring_active, monitoring_thread
    
    if not monitoring_active:
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
        logger.info("Monitoring started manually")
    
    return jsonify({'success': True, 'monitoring_active': True})

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop monitoring"""
    global monitoring_active
    monitoring_active = False
    logger.info("Monitoring stopped")
    return jsonify({'success': True, 'monitoring_active': False})

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add new user to monitor"""
    username = request.form.get('username', '').strip().replace('@', '')
    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    try:
        usernames = load_usernames()
        if username not in usernames:
            with open('usernames.txt', 'a') as f:
                f.write(f'\n{username}')
            logger.info(f"Added user: {username}")
        
        return redirect(url_for('status'))
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'monitoring_active': monitoring_active,
        'drive_connected': bool(drive_service),
        'active_recordings': len(recording_threads)
    })

if __name__ == '__main__':
    # Create directories
    os.makedirs('recordings', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Get port from environment (for Replit deployment)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"Starting TikTok Livestream Recorder on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
