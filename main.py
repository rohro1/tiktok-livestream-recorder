import os
import json
import time
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_AUTH_AVAILABLE = True
except ImportError as e:
    print(f"Google Auth not available: {e}")
    Flow = None
    Credentials = None
    build = None
    MediaFileUpload = None
    GOOGLE_AUTH_AVAILABLE = False
import requests
import yt_dlp
import subprocess
import re
import threading
import schedule
from urllib.parse import unquote

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
app.secret_key = os.environ.get('SECRET_KEY', 'tiktok-recorder-secret-key-2024')

# Global variables
monitoring_active = False
monitoring_thread = None
drive_service = None
status_tracker = {}
recording_threads = {}

class TikTokChecker:
    """Enhanced TikTok live status checker with updated detection methods"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })
    
    def is_live(self, username):
        """Enhanced live detection with updated methods for 2025"""
        try:
            logger.info(f"🔍 Checking live status for @{username}")
            
            # Method 1: Direct profile page analysis (most reliable)
            try:
                profile_url = f"https://www.tiktok.com/@{username}"
                response = self.session.get(profile_url, timeout=15)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Look for live stream indicators in the HTML
                    live_patterns = [
                        r'"live_room":\s*{[^}]*"status":\s*2',
                        r'"roomStatus":\s*2',
                        r'"liveRoomUserInfo":\s*{[^}]*"roomId"',
                        r'"isLive":\s*true',
                        r'"user_live_status":\s*1',
                        r'live_room.*?status.*?2',
                        r'roomId.*?[0-9]{10,}',
                        r'"live":\s*true'
                    ]
                    
                    for pattern in live_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            logger.info(f"✅ Profile Analysis: {username} is LIVE! (Pattern: {pattern[:30]}...)")
                            return True
                    
                    # Check for live room URL in the page
                    live_url_pattern = r'https://www\.tiktok\.com/@' + re.escape(username) + r'/live'
                    if re.search(live_url_pattern, content):
                        logger.info(f"✅ Live URL found: {username} is LIVE!")
                        return True
                        
            except Exception as e:
                logger.debug(f"Profile analysis failed for {username}: {e}")
            
            # Method 2: Try accessing live URL directly
            try:
                live_url = f"https://www.tiktok.com/@{username}/live"
                live_response = self.session.get(live_url, timeout=10, allow_redirects=False)
                
                # If we get a 200 or 302 to a live room, user might be live
                if live_response.status_code in [200, 302]:
                    if live_response.status_code == 302:
                        redirect_url = live_response.headers.get('Location', '')
                        if 'live' in redirect_url and username in redirect_url:
                            logger.info(f"✅ Live Redirect: {username} is LIVE!")
                            return True
                    elif live_response.status_code == 200:
                        # Check if the live page actually has live content
                        live_content = live_response.text
                        if any(indicator in live_content.lower() for indicator in [
                            'live_room', 'roomid', '"live":true', 'broadcasting', 'viewer'
                        ]):
                            logger.info(f"✅ Live Page: {username} is LIVE!")
                            return True
                            
            except Exception as e:
                logger.debug(f"Live URL check failed for {username}: {e}")
            
            # Method 3: Mobile API approach (alternative endpoint)
            try:
                # Use mobile user agent for different API response
                mobile_headers = self.session.headers.copy()
                mobile_headers.update({
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
                })
                
                mobile_url = f"https://m.tiktok.com/@{username}"
                mobile_response = requests.get(mobile_url, headers=mobile_headers, timeout=10)
                
                if mobile_response.status_code == 200:
                    mobile_content = mobile_response.text.lower()
                    mobile_indicators = ['live', 'broadcasting', 'viewer', 'room']
                    
                    # Count indicators to reduce false positives
                    indicator_count = sum(1 for indicator in mobile_indicators if indicator in mobile_content)
                    if indicator_count >= 2:
                        logger.info(f"✅ Mobile Check: {username} is LIVE! (Indicators: {indicator_count})")
                        return True
                        
            except Exception as e:
                logger.debug(f"Mobile API check failed for {username}: {e}")
            
            # Method 4: yt-dlp verification (fallback)
            try:
                live_url = f"https://www.tiktok.com/@{username}/live"
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'skip_download': True,
                    'no_check_certificate': True,
                    'socket_timeout': 8
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(live_url, download=False)
                        if info and (info.get('is_live') or info.get('live_status') == 'is_live'):
                            logger.info(f"✅ yt-dlp Method: {username} is LIVE!")
                            return True
                    except yt_dlp.DownloadError as e:
                        if "live" not in str(e).lower():
                            logger.debug(f"yt-dlp error for {username}: {e}")
            except Exception as e:
                logger.debug(f"yt-dlp method failed for {username}: {e}")
            
            logger.debug(f"⚪ {username} is not live")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking live status for {username}: {e}")
            return False

class StreamRecorder:
    """Enhanced stream recorder with better error handling"""
    
    def __init__(self):
        self.recordings_dir = "recordings"
        os.makedirs(self.recordings_dir, exist_ok=True)
    
    def record_stream(self, username):
        """Record a TikTok livestream with enhanced options"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(self.recordings_dir, f"{username}_{timestamp}.mp4")
            
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            # Enhanced yt-dlp options for better compatibility
            ydl_opts = {
                'format': 'best[height<=720]/best',
                'outtmpl': output_file,
                'no_warnings': False,
                'extractaudio': False,
                'embed_subs': False,
                'writesubtitles': False,
                'writeautomaticsub': False,
                'ignoreerrors': False,
                'no_check_certificate': True,
                'prefer_ffmpeg': True,
                'hls_prefer_native': True,
                'live_from_start': True,
                'wait_for_video': (5, 60),
                'fragment_retries': 10,
                'retry_sleep_functions': {'http': lambda n: min(2 * n, 30)},
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            
            logger.info(f"🎬 Starting recording for {username}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([live_url])
                    
                    # Check if file was created successfully
                    if os.path.exists(output_file) and os.path.getsize(output_file) > 10240:  # At least 10KB
                        logger.info(f"✅ Recording completed: {output_file}")
                        return output_file
                    else:
                        logger.error(f"❌ Recording file too small or not created for {username}")
                        return None
                        
                except Exception as e:
                    logger.error(f"❌ yt-dlp recording failed for {username}: {e}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Recording error for {username}: {e}")
            return None

class GoogleDriveUploader:
    """Upload files to Google Drive with enhanced folder management"""
    
    def __init__(self, service):
        self.service = service
        self.folder_cache = {}  # Cache folder IDs to avoid repeated API calls
    
    def create_user_folders(self, usernames):
        """Create folder structure for all users upfront"""
        try:
            if not self.service:
                logger.error("Google Drive service not initialized")
                return False
            
            logger.info(f"📁 Creating folder structure for {len(usernames)} users...")
            
            # Create main folder
            main_folder_id = self._get_or_create_folder('TikTok Recordings')
            
            # Create user folders
            for username in usernames:
                user_folder_id = self._get_or_create_folder(username, main_folder_id)
                
                # Create current month folder
                date_folder = datetime.now().strftime('%Y-%m')
                date_folder_id = self._get_or_create_folder(date_folder, user_folder_id)
                
                # Cache the structure
                self.folder_cache[username] = {
                    'main': main_folder_id,
                    'user': user_folder_id,
                    'current_month': date_folder_id
                }
                
                logger.info(f"📂 Created folder structure for @{username}")
            
            logger.info("✅ All folder structures created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating user folders: {e}")
            return False
    
    def upload_video(self, file_path, username):
        """Upload video file to Google Drive"""
        try:
            if not self.service:
                logger.error("Google Drive service not initialized")
                return None
            
            # Get or create folder structure
            date_folder = datetime.now().strftime('%Y-%m')
            
            if username in self.folder_cache:
                # Check if we need to create a new month folder
                cached_month = self.folder_cache[username].get('current_month_name')
                if cached_month != date_folder:
                    # Create new month folder
                    user_folder_id = self.folder_cache[username]['user']
                    date_folder_id = self._get_or_create_folder(date_folder, user_folder_id)
                    self.folder_cache[username]['current_month'] = date_folder_id
                    self.folder_cache[username]['current_month_name'] = date_folder
                
                target_folder_id = self.folder_cache[username]['current_month']
            else:
                # Create folder structure for new user
                main_folder_id = self._get_or_create_folder('TikTok Recordings')
                user_folder_id = self._get_or_create_folder(username, main_folder_id)
                date_folder_id = self._get_or_create_folder(date_folder, user_folder_id)
                target_folder_id = date_folder_id
            
            # Upload file
            filename = os.path.basename(file_path)
            file_metadata = {
                'name': filename,
                'parents': [target_folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink'
            ).execute()
            
            logger.info(f"📁 Uploaded {filename} to Google Drive")
            return file.get('webViewLink')
            
        except Exception as e:
            logger.error(f"Drive upload error: {e}")
            return None
    
    def _get_or_create_folder(self, name, parent_id=None):
        """Get existing folder or create new one"""
        try:
            # Create cache key
            cache_key = f"{name}_{parent_id or 'root'}"
            if cache_key in self.folder_cache:
                return self.folder_cache[cache_key]
            
            # Search for existing folder
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if items:
                folder_id = items[0]['id']
                self.folder_cache[cache_key] = folder_id
                return folder_id
            
            # Create new folder
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            self.folder_cache[cache_key] = folder_id
            return folder_id
            
        except Exception as e:
            logger.error(f"Error creating folder {name}: {e}")
            return None

def load_usernames():
    """Load usernames from file"""
    try:
        if os.path.exists('usernames.txt'):
            with open('usernames.txt', 'r', encoding='utf-8') as f:
                usernames = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Clean username
                        username = line.replace('@', '').strip()
                        if username and username not in usernames:
                            usernames.append(username)
                return usernames
        return []
    except Exception as e:
        logger.error(f"Error loading usernames: {e}")
        return []

def save_usernames(usernames):
    """Save usernames to file"""
    try:
        with open('usernames.txt', 'w', encoding='utf-8') as f:
            f.write("# TikTok Livestream Recorder - Usernames Configuration\n")
            f.write("# Add TikTok usernames here (one per line, without @)\n")
            f.write("# Lines starting with # are comments and will be ignored\n\n")
            for username in usernames:
                f.write(f"{username}\n")
        return True
    except Exception as e:
        logger.error(f"Error saving usernames: {e}")
        return False

def update_status(username, **kwargs):
    """Update user status in tracker"""
    if username not in status_tracker:
        status_tracker[username] = {}
    
    status_tracker[username].update(kwargs)
    status_tracker[username]['last_updated'] = datetime.now().isoformat()

def load_google_credentials():
    """Load Google credentials from environment or file"""
    try:
        # Try environment variable first
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            return json.loads(creds_json)
        
        # Fallback to file
        if os.path.exists('credentials.json'):
            with open('credentials.json', 'r') as f:
                return json.load(f)
        
        logger.error("❌ No Google credentials found!")
        return None
    except Exception as e:
        logger.error(f"❌ Error loading credentials: {e}")
        return None

def record_user_stream(username, checker, recorder, uploader):
    """Record a user's livestream in separate thread"""
    try:
        logger.info(f"🎬 Recording thread started for {username}")
        update_status(username, is_recording=True, recording_start=datetime.now().isoformat())
        
        # Record the stream
        output_file = recorder.record_stream(username)
        
        if output_file and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            logger.info(f"✅ Recording completed for {username}: {file_size} bytes")
            
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
                        logger.info(f"📁 Uploaded and cleaned up: {username}")
                    else:
                        logger.error(f"❌ Drive upload failed for {username}")
                except Exception as e:
                    logger.error(f"❌ Drive upload error for {username}: {e}")
        else:
            logger.error(f"❌ Recording failed for {username}")
        
        update_status(username, is_recording=False)
        
    except Exception as e:
        logger.error(f"❌ Recording thread error for {username}: {e}")
        update_status(username, is_recording=False, error=str(e))
    finally:
        # Clean up thread reference
        if username in recording_threads:
            del recording_threads[username]

def auto_commit_job():
    """Run auto-commit in background"""
    try:
        logger.info("🔄 Running auto-commit...")
        result = subprocess.run(['python', 'auto_commit.py'], 
                              capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("✅ Auto-commit successful")
        else:
            logger.error(f"❌ Auto-commit failed: {result.stderr}")
    except Exception as e:
        logger.error(f"❌ Auto-commit error: {e}")

def schedule_auto_commits():
    """Schedule automatic commits every 30 minutes"""
    schedule.every(30).minutes.do(auto_commit_job)
    
    while monitoring_active:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def monitoring_loop():
    """Main monitoring loop with enhanced live detection"""
    global monitoring_active, drive_service
    
    logger.info("🚀 Starting monitoring loop")
    monitoring_active = True
    
    # Initialize components
    checker = TikTokChecker()
    recorder = StreamRecorder()
    uploader = GoogleDriveUploader(drive_service) if drive_service else None
    
    # Create folder structure for all users upfront
    if uploader:
        usernames = load_usernames()
        if usernames:
            uploader.create_user_folders(usernames)
    
    # Start auto-commit scheduler in background
    commit_thread = threading.Thread(target=schedule_auto_commits, daemon=True)
    commit_thread.start()
    logger.info("🔄 Auto-commit scheduler started")
    
    check_interval = 30  # seconds between full cycles
    user_check_interval = 3  # seconds between users
    
    while monitoring_active:
        try:
            usernames = load_usernames()
            if not usernames:
                logger.info("⚠️ No usernames to monitor")
                time.sleep(60)
                continue
            
            logger.info(f"🔍 Checking {len(usernames)} users...")
            
            for username in usernames:
                if not monitoring_active:
                    break
                
                try:
                    # Check if user is live
                    is_live = checker.is_live(username)
                    
                    current_time = datetime.now().isoformat()
                    update_status(username, 
                                 is_live=is_live,
                                 last_check=current_time)
                    
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
                            logger.info(f"🎬 Started recording {username}")
                        else:
                            logger.info(f"📹 Already recording {username}")
                    else:
                        logger.debug(f"⚪ {username} is offline")
                    
                except Exception as e:
                    logger.error(f"❌ Error checking {username}: {e}")
                    update_status(username, error=str(e))
                
                # Small delay between user checks
                time.sleep(user_check_interval)
            
            # Wait before next cycle
            logger.info(f"⏱️ Waiting {check_interval}s before next cycle...")
            time.sleep(check_interval)
            
        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
            time.sleep(60)
    
    logger.info("🛑 Monitoring loop stopped")

# Routes
@app.route('/')
def home():
    """Home page - redirect to authorization or status"""
    if drive_service:
        return redirect(url_for('status'))
    else:
        return redirect(url_for('authorize'))

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
            if field in data and data[field]:
                try:
                    dt = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
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
        if not GOOGLE_AUTH_AVAILABLE:
            return "❌ Google Auth libraries not available. Please check dependencies.", 500
            
        creds_info = load_google_credentials()
        if not creds_info:
            return "❌ Google credentials not found. Please add credentials.json file.", 500
        
        # Get the redirect URI from environment or construct it
        redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
        if not redirect_uri:
            # Auto-detect based on request
            if request.host.endswith('.onrender.com'):
                redirect_uri = f"https://{request.host}/oauth2callback"
            else:
                redirect_uri = f"{request.scheme}://{request.host}/oauth2callback"
        
        logger.info(f"🔗 Using OAuth redirect URI: {redirect_uri}")
        
        flow = Flow.from_client_config(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive.file'],
            redirect_uri=redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        session['redirect_uri'] = redirect_uri
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"❌ OAuth initiation error: {e}")
        return f"Authorization setup failed: {e}", 500

@app.route('/oauth2callback')
def oauth2callback():
    """Handle OAuth callback and auto-start monitoring"""
    global drive_service, monitoring_thread
    
    try:
        if not GOOGLE_AUTH_AVAILABLE:
            return "❌ Google Auth libraries not available. Please check dependencies.", 500
            
        creds_info = load_google_credentials()
        redirect_uri = session.get('redirect_uri')
        
        flow = Flow.from_client_config(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive.file'],
            redirect_uri=redirect_uri
        )
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Initialize Drive service
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Test the connection
        about = drive_service.about().get(fields="user").execute()
        user_email = about.get('user', {}).get('emailAddress', 'Unknown')
        logger.info(f"✅ Google Drive connected successfully for {user_email}")
        
        # Auto-start monitoring after successful authorization
        if not monitoring_active and monitoring_thread is None:
            monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
            monitoring_thread.start()
            logger.info("🚀 Auto-started monitoring after authorization")
        
        return redirect(url_for('status'))
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        return f"Authorization failed: {e}", 500

@app.route('/authorize')
def authorize():
    """Authorization page"""
    usernames = load_usernames()  # Load usernames to display on auth page
    return render_template('authorize.html', 
                         drive_connected=bool(drive_service),
                         usernames=usernames)

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Manually start monitoring"""
    global monitoring_active, monitoring_thread
    
    if not monitoring_active:
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
        logger.info("🚀 Monitoring started manually")
        return jsonify({'success': True, 'message': 'Monitoring started'})
    else:
        return jsonify({'success': True, 'message': 'Monitoring already active'})

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop monitoring"""
    global monitoring_active
    monitoring_active = False
    logger.info("🛑 Monitoring stopped")
    return jsonify({'success': True, 'message': 'Monitoring stopped'})

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add new user to monitor"""
    username = request.form.get('username', '').strip().replace('@', '')
    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    try:
        usernames = load_usernames()
        if username not in usernames:
            usernames.append(username)
            if save_usernames(usernames):
                logger.info(f"➕ Added user: {username}")
                
                # Create folder structure for new user if Drive is connected
                if drive_service:
                    uploader = GoogleDriveUploader(drive_service)
                    uploader.create_user_folders([username])
                    
            else:
                logger.error(f"❌ Failed to save username: {username}")
                return jsonify({'error': 'Failed to save username'}), 500
        else:
            logger.info(f"ℹ️ User {username} already exists")
        
        return redirect(url_for('status'))
    except Exception as e:
        logger.error(f"❌ Error adding user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/remove_user', methods=['POST'])
def remove_user():
    """Remove user from monitoring"""
    username = request.form.get('username', '').strip().replace('@', '')
    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    try:
        usernames = load_usernames()
        if username in usernames:
            usernames.remove(username)
            if save_usernames(usernames):
                logger.info(f"➖ Removed user: {username}")
                
                # Stop recording if active
                if username in recording_threads:
                    del recording_threads[username]
                
                # Remove from status tracker
                if username in status_tracker:
                    del status_tracker[username]
            else:
                logger.error(f"❌ Failed to remove username: {username}")
                return jsonify({'error': 'Failed to remove username'}), 500
        else:
            logger.info(f"ℹ️ User {username} not found")
        
        return redirect(url_for('status'))
    except Exception as e:
        logger.error(f"❌ Error removing user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitoring_active,
        'active_recordings': len(recording_threads),
        'drive_connected': bool(drive_service),
        'usernames_count': len(load_usernames())
    })

@app.route('/api/usernames')
def api_usernames():
    """API endpoint to get current usernames"""
    return jsonify({
        'usernames': load_usernames(),
        'count': len(load_usernames())
    })

if __name__ == '__main__':
    # Get port from environment variable (required for Render)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info("🚀 Starting TikTok Livestream Recorder")
    logger.info(f"🌐 Running on port {port}")
    
    usernames = load_usernames()
    logger.info(f"👥 Monitoring {len(usernames)} users: {', '.join(usernames) if usernames else 'None'}")
    
    if not load_google_credentials():
        logger.warning("⚠️ Google credentials not found - Google Drive features will be disabled")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
