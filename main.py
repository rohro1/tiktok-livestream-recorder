
import os
import json
import time
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from google.oauth2.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests
import yt_dlp
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Global variables
monitoring_active = False
monitoring_thread = None
drive_service = None
status_tracker = {}
recording_threads = {}

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
    """Record TikTok livestreams"""
    
    def __init__(self):
        self.recordings_dir = "recordings"
        os.makedirs(self.recordings_dir, exist_ok=True)
    
    def record_stream(self, username):
        """Record a TikTok livestream"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(self.recordings_dir, f"{username}_{timestamp}.mp4")
            
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            # Use yt-dlp to get stream URL and record with ffmpeg
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'best[height<=480]',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(live_url, download=False)
                if info and 'url' in info:
                    stream_url = info['url']
                    
                    # Record with ffmpeg
                    cmd = [
                        'ffmpeg',
                        '-i', stream_url,
                        '-c', 'copy',
                        '-t', '3600',  # Max 1 hour
                        '-y',  # Overwrite output files
                        output_file
                    ]
                    
                    logger.info(f"Starting recording for {username}")
                    process = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                    
                    if process.returncode == 0 and os.path.exists(output_file):
                        logger.info(f"Recording completed: {output_file}")
                        return output_file
                    else:
                        logger.error(f"Recording failed for {username}: {process.stderr}")
                        return None
                        
        except Exception as e:
            logger.error(f"Recording error for {username}: {e}")
            return None

class GoogleDriveUploader:
    """Upload files to Google Drive"""
    
    def __init__(self, service):
        self.service = service
    
    def upload_video(self, file_path, username):
        """Upload video file to Google Drive"""
        try:
            if not self.service:
                logger.error("Google Drive service not initialized")
                return None
            
            # Create folder structure: TikTok Recordings/username/YYYY-MM
            date_folder = datetime.now().strftime('%Y-%m')
            
            # Find or create main folder
            main_folder_id = self._get_or_create_folder('TikTok Recordings')
            user_folder_id = self._get_or_create_folder(username, main_folder_id)
            date_folder_id = self._get_or_create_folder(date_folder, user_folder_id)
            
            # Upload file
            filename = os.path.basename(file_path)
            file_metadata = {
                'name': filename,
                'parents': [date_folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink'
            ).execute()
            
            logger.info(f"Uploaded {filename} to Google Drive")
            return file.get('webViewLink')
            
        except Exception as e:
            logger.error(f"Drive upload error: {e}")
            return None
    
    def _get_or_create_folder(self, name, parent_id=None):
        """Get existing folder or create new one"""
        try:
            # Search for existing folder
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(q=query).execute()
            items = results.get('files', [])
            
            if items:
                return items[0]['id']
            
            # Create new folder
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            return folder.get('id')
            
        except Exception as e:
            logger.error(f"Error creating folder {name}: {e}")
            return None

def load_usernames():
    """Load usernames from file"""
    try:
        if os.path.exists('usernames.txt'):
            with open('usernames.txt', 'r') as f:
                usernames = [line.strip().replace('@', '') for line in f if line.strip()]
                return [u for u in usernames if u]
        return []
    except Exception as e:
        logger.error(f"Error loading usernames: {e}")
        return []

def update_status(username, **kwargs):
    """Update user status in tracker"""
    if username not in status_tracker:
        status_tracker[username] = {}
    
    status_tracker[username].update(kwargs)
    status_tracker[username]['last_updated'] = datetime.now().isoformat()

def load_google_credentials():
    """Load Google credentials from credentials.json file"""
    try:
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
        
        update_status(username, is_recording=False)
        
    except Exception as e:
        logger.error(f"Recording thread error for {username}: {e}")
        update_status(username, is_recording=False, error=str(e))
    finally:
        # Clean up thread reference
        if username in recording_threads:
            del recording_threads[username]

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

# Routes
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
    """API endpoint for status data"""
    usernames = load_usernames()
    user_data = []
    
    for username in usernames:
        data = status_tracker.get(username, {})
        data['username'] = username
        data['is_recording'] = username in recording_threads
        user_data.append(data)
    
    return jsonify({
        'users': user_data,
        'monitoring_active': monitoring_active,
        'drive_connected': bool(drive_service),
        'total_recordings': len(recording_threads),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/auth/google')
def auth_google():
    """Start Google OAuth flow"""
    try:
        creds_info = load_google_credentials()
        if not creds_info:
            return "Google credentials not found. Please add credentials.json file.", 500
        
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
        logger.error(f"OAuth initiation error: {e}")
        return f"Authorization setup failed: {e}", 500

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

@app.route('/authorize')
def authorize():
    """Authorization page"""
    return render_template('authorize.html', drive_connected=bool(drive_service))

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
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitoring_active,
        'active_recordings': len(recording_threads)
    })

if __name__ == '__main__':
    # Get port from environment variable (required for Render)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"Starting TikTok Livestream Recorder on port {port}")
    logger.info(f"Monitoring {len(load_usernames())} users")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
