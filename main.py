#!/usr/bin/env python3
"""
TikTok Livestream Recorder - Production Version
Automatically monitors TikTok users and records their livestreams
"""

import os
import time
import json
import logging
import requests
import subprocess
import threading
import yt_dlp
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import signal
import sys
from pathlib import Path
import hashlib
import secrets
import psutil

# Flask app configuration
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
RECORDINGS_DIR = "recordings"
USERNAMES_FILE = "usernames.txt"
CHECK_INTERVAL = 30  # seconds between checks
RECORDING_QUALITY = "best[height<=480]/best"  # 480p max quality

# Global state
monitoring_active = False
monitoring_thread = None
recording_processes = {}
live_status = {}
last_check_times = {}
drive_service = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class StreamRecorder:
    def __init__(self):
        self.ensure_directories()
        
    def ensure_directories(self):
        """Create necessary directories"""
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        os.makedirs('templates', exist_ok=True)
        
        # Create usernames.txt if it doesn't exist
        if not os.path.exists(USERNAMES_FILE):
            with open(USERNAMES_FILE, 'w', encoding='utf-8') as f:
                f.write("# Add TikTok usernames here (one per line, without @)\n")
                f.write("# Lines starting with # are comments\n\n")
    
    def load_usernames(self):
        """Load usernames from file"""
        try:
            with open(USERNAMES_FILE, 'r', encoding='utf-8') as f:
                usernames = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        username = line.replace('@', '').strip()
                        if username:
                            usernames.append(username)
                return list(set(usernames))  # Remove duplicates
        except FileNotFoundError:
            return []
    
    def save_usernames(self, usernames):
        """Save usernames to file"""
        try:
            with open(USERNAMES_FILE, 'w', encoding='utf-8') as f:
                f.write("# TikTok Livestream Recorder - Usernames\n")
                f.write("# Add usernames below (one per line, without @)\n\n")
                for username in sorted(set(usernames)):
                    if username.strip():
                        f.write(f"{username.strip()}\n")
            logger.info(f"💾 Saved {len(usernames)} usernames to file")
        except Exception as e:
            logger.error(f"❌ Error saving usernames: {e}")
    
    def add_username(self, username):
        """Add a username to monitoring list"""
        username = username.replace('@', '').strip()
        if not username:
            return False
            
        usernames = self.load_usernames()
        if username not in usernames:
            usernames.append(username)
            self.save_usernames(usernames)
            self.create_user_folder(username)
            logger.info(f"➕ Added username: {username}")
            return True
        return False
    
    def remove_username(self, username):
        """Remove a username from monitoring list"""
        username = username.replace('@', '').strip()
        usernames = self.load_usernames()
        if username in usernames:
            usernames.remove(username)
            self.save_usernames(usernames)
            # Stop recording if active
            if username in recording_processes:
                self.stop_recording(username)
            logger.info(f"➖ Removed username: {username}")
            return True
        return False
    
    def create_user_folder(self, username):
        """Create folder structure for user"""
        user_dir = os.path.join(RECORDINGS_DIR, username)
        os.makedirs(user_dir, exist_ok=True)
        logger.info(f"📁 Created folder for {username}")
    
    def check_live_status_advanced(self, username):
        """Enhanced live status detection using multiple reliable methods"""
        try:
            clean_username = username.replace('@', '').strip()
            
            # Method 1: TikTok mobile API (more reliable)
            mobile_api_url = f"https://m.tiktok.com/api/user/detail/?uniqueId={clean_username}"
            headers = {
                'User-Agent': 'TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            response = requests.get(mobile_api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    user_detail = data.get('userInfo', {}).get('user', {})
                    room_id = user_detail.get('roomId', '')
                    if room_id and room_id != '' and room_id != '0':
                        logger.info(f"✅ Mobile API: {username} is LIVE! (Room: {room_id})")
                        return True
                except:
                    pass
            
            # Method 2: Check live room directly
            if response.status_code == 200:
                try:
                    data = response.json()
                    user_detail = data.get('userInfo', {}).get('user', {})
                    room_id = user_detail.get('roomId', '')
                    
                    if room_id and room_id != '' and room_id != '0':
                        # Verify room is actually live
                        room_url = f"https://webcast.tiktok.com/webcast/room/info/?room_id={room_id}"
                        room_response = requests.get(room_url, headers=headers, timeout=10)
                        
                        if room_response.status_code == 200:
                            room_data = room_response.json()
                            room_info = room_data.get('data', {}).get('room', {})
                            if room_info.get('status') == 2:  # 2 = live
                                logger.info(f"✅ Room API: {username} is LIVE! (Verified)")
                                return True
                except:
                    pass
            
            # Method 3: Alternative web endpoint
            web_api_url = f"https://www.tiktok.com/api/user/detail/?uniqueId={clean_username}"
            web_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Referer': f'https://www.tiktok.com/@{clean_username}'
            }
            
            response = requests.get(web_api_url, headers=web_headers, timeout=10)
            if response.status_code == 200:
                try:
                    data = response.json()
                    user_info = data.get('userInfo', {}).get('user', {})
                    room_id = user_info.get('roomId', '')
                    if room_id and room_id != '' and room_id != '0':
                        logger.info(f"✅ Web API: {username} is LIVE!")
                        return True
                except:
                    pass
            
            logger.info(f"❌ All checks: {username} is not live")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking {username}: {e}")
            return False
    
    def get_stream_url(self, username):
        """Get stream URL for recording using updated yt-dlp"""
        try:
            clean_username = username.replace('@', '').strip()
            live_url = f"https://www.tiktok.com/@{clean_username}/live"
            
            ydl_opts = {
                'quiet': False,
                'no_warnings': False,
                'format': RECORDING_QUALITY,
                'timeout': 30,
                'extractor_args': {
                    'tiktok': {
                        'webpage_url_basename': 'live'
                    }
                },
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(live_url, download=False)
                if info and info.get('url'):
                    logger.info(f"🔗 Got stream URL for {username}")
                    return info['url']
                elif info and info.get('formats'):
                    # Try to get URL from formats
                    for fmt in info['formats']:
                        if fmt.get('url'):
                            logger.info(f"🔗 Got stream URL from formats for {username}")
                            return fmt['url']
            
            return None
            
        except yt_dlp.utils.DownloadError as e:
            if "not currently live" in str(e):
                logger.info(f"❌ {username} is not live (yt-dlp confirmed)")
            else:
                logger.error(f"❌ yt-dlp error for {username}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error getting stream URL for {username}: {e}")
            return None
    
    def start_recording(self, username):
        """Start recording with FFmpeg"""
        if username in recording_processes:
            logger.info(f"📹 Already recording {username}")
            return False
        
        try:
            # Get stream URL
            stream_url = self.get_stream_url(username)
            if not stream_url:
                logger.error(f"❌ No stream URL for {username}")
                return False
            
            # Create user folder
            self.create_user_folder(username)
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{username}_{timestamp}.mp4"
            user_dir = os.path.join(RECORDINGS_DIR, username)
            filepath = os.path.join(user_dir, filename)
            
            # FFmpeg command for reliable recording
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'ultrafast',  # Faster encoding for live streams
                '-crf', '30',           # Higher CRF for smaller files at 480p
                '-maxrate', '800k',     # Lower bitrate for 480p
                '-bufsize', '1600k',    # Buffer size
                '-vf', 'scale=-2:480',  # Force 480p resolution
                '-f', 'mp4',
                '-movflags', '+faststart',
                '-reconnect', '1',      # Auto-reconnect on connection loss
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
                '-y',
                filepath
            ]
            
            logger.info(f"🎬 Starting FFmpeg recording for {username}")
            logger.info(f"📁 Output: {filepath}")
            
            # Start FFmpeg process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Store recording info
            recording_processes[username] = {
                'process': process,
                'filename': filename,
                'filepath': filepath,
                'start_time': datetime.now(),
                'stream_url': stream_url,
                'cmd': ' '.join(cmd)
            }
            
            logger.info(f"✅ Recording started for {username} (PID: {process.pid})")
            
            # Start monitoring thread for this recording
            monitor_thread = threading.Thread(
                target=self.monitor_recording,
                args=(username,),
                daemon=True
            )
            monitor_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error starting recording for {username}: {e}")
            return False
    
    def monitor_recording(self, username):
        """Monitor a specific recording process"""
        try:
            if username not in recording_processes:
                return
            
            process = recording_processes[username]['process']
            filepath = recording_processes[username]['filepath']
            start_time = recording_processes[username]['start_time']
            
            logger.info(f"👁️ Monitoring recording for {username}")
            
            while process.poll() is None:
                # Check if file exists and is growing
                if os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                    duration = datetime.now() - start_time
                    
                    logger.info(f"📊 {username}: {duration.total_seconds():.0f}s, {file_size/1024/1024:.1f}MB")
                else:
                    logger.warning(f"⚠️ Recording file not found: {filepath}")
                
                time.sleep(10)  # Check every 10 seconds
            
            # Process ended
            return_code = process.returncode
            duration = datetime.now() - start_time
            
            if return_code == 0:
                logger.info(f"✅ Recording completed for {username} ({duration.total_seconds():.0f}s)")
            else:
                # Get error output
                stderr_output = process.stderr.read() if process.stderr else "No error output"
                logger.error(f"❌ Recording failed for {username} (code: {return_code}): {stderr_output}")
            
            # Check final file
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                if file_size > 1024:  # At least 1KB
                    logger.info(f"💾 Recording saved: {filepath} ({file_size/1024/1024:.1f}MB)")
                    
                    # Upload to Google Drive if authorized
                    if drive_service:
                        self.upload_to_drive(filepath, username)
                else:
                    logger.warning(f"⚠️ Recording file too small or empty: {filepath}")
                    try:
                        os.remove(filepath)
                    except:
                        pass
            
            # Clean up
            if username in recording_processes:
                del recording_processes[username]
                
        except Exception as e:
            logger.error(f"❌ Error monitoring recording for {username}: {e}")
            if username in recording_processes:
                del recording_processes[username]
    
    def stop_recording(self, username):
        """Stop recording for a user"""
        if username not in recording_processes:
            return False
        
        try:
            process = recording_processes[username]['process']
            
            # Send SIGTERM for graceful shutdown
            process.terminate()
            
            # Wait for graceful termination
            try:
                process.wait(timeout=15)
                logger.info(f"🛑 Gracefully stopped recording for {username}")
            except subprocess.TimeoutExpired:
                # Force kill if needed
                process.kill()
                process.wait()
                logger.warning(f"🔪 Force killed recording for {username}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error stopping recording for {username}: {e}")
            return False
    
    def upload_to_drive(self, filepath, username):
        """Upload recording to Google Drive with organized folders"""
        try:
            if not drive_service:
                logger.warning("❌ Google Drive not connected")
                return False
            
            # Create folder structure: TikTok_Recordings/Username/YYYY-MM/
            current_date = datetime.now()
            year_month = current_date.strftime('%Y-%m')
            
            # Get or create main folder
            main_folder_id = self.get_or_create_folder(drive_service, "TikTok_Recordings")
            
            # Get or create user folder
            user_folder_id = self.get_or_create_folder(drive_service, username, main_folder_id)
            
            # Get or create date folder
            date_folder_id = self.get_or_create_folder(drive_service, year_month, user_folder_id)
            
            # Upload file
            filename = os.path.basename(filepath)
            file_metadata = {
                'name': filename,
                'parents': [date_folder_id]
            }
            
            media = MediaFileUpload(filepath, resumable=True)
            
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink'
            ).execute()
            
            file_id = file.get('id')
            web_link = file.get('webViewLink')
            
            logger.info(f"☁️ Uploaded to Drive: {filename} (ID: {file_id})")
            
            # Remove local file after successful upload
            try:
                os.remove(filepath)
                logger.info(f"🗑️ Removed local file: {filepath}")
            except Exception as e:
                logger.warning(f"⚠️ Could not remove local file: {e}")
            
            return web_link
            
        except Exception as e:
            logger.error(f"❌ Drive upload failed for {username}: {e}")
            return False
    
    def get_or_create_folder(self, service, folder_name, parent_id=None):
        """Get or create a folder in Google Drive"""
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = service.files().list(
                q=query,
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
                
                if parent_id:
                    folder_metadata['parents'] = [parent_id]
                
                folder = service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                folder_id = folder.get('id')
                logger.info(f"📁 Created Drive folder: {folder_name} (ID: {folder_id})")
                return folder_id
                
        except Exception as e:
            logger.error(f"❌ Error with Drive folder {folder_name}: {e}")
            return None

# Initialize recorder
recorder = StreamRecorder()

def setup_drive_service():
    """Setup Google Drive service"""
    global drive_service
    try:
        if 'credentials' in session:
            creds_data = session['credentials']
            creds = Credentials.from_authorized_user_info(creds_data)
            
            # Refresh if needed
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Update session with new token
                session['credentials'] = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }
            
            drive_service = build('drive', 'v3', credentials=creds)
            logger.info("✅ Google Drive service initialized")
            return True
    except Exception as e:
        logger.error(f"❌ Error setting up Drive service: {e}")
        drive_service = None
    return False

def monitoring_loop():
    """Main monitoring loop"""
    global monitoring_active
    
    logger.info("🔄 Monitoring loop started")
    
    while monitoring_active:
        try:
            usernames = recorder.load_usernames()
            logger.info(f"🔍 Checking {len(usernames)} users...")
            
            for username in usernames:
                if not monitoring_active:
                    break
                
                try:
                    # Update last check time
                    last_check_times[username] = datetime.now()
                    
                    # Check live status
                    is_live = recorder.check_live_status_advanced(username)
                    live_status[username] = is_live
                    
                    if is_live:
                        logger.info(f"🔴 {username} is LIVE!")
                        
                        # Start recording if not already recording
                        if username not in recording_processes:
                            logger.info(f"🎬 Starting recording for {username}")
                            success = recorder.start_recording(username)
                            if success:
                                logger.info(f"✅ Recording started for {username}")
                            else:
                                logger.error(f"❌ Failed to start recording for {username}")
                        else:
                            # Check if recording process is still alive
                            process = recording_processes[username]['process']
                            if process.poll() is not None:
                                logger.warning(f"⚠️ Recording process died for {username}, restarting...")
                                del recording_processes[username]
                                recorder.start_recording(username)
                            else:
                                duration = datetime.now() - recording_processes[username]['start_time']
                                logger.info(f"📹 Still recording {username} ({duration.total_seconds():.0f}s)")
                    else:
                        # User is not live
                        if username in recording_processes:
                            logger.info(f"🛑 {username} went offline, stopping recording")
                            recorder.stop_recording(username)
                    
                    # Small delay between user checks
                    time.sleep(3)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {username}: {e}")
                    live_status[username] = False
            
            # Wait before next full cycle
            logger.info(f"⏱️ Waiting {CHECK_INTERVAL}s before next cycle...")
            for i in range(CHECK_INTERVAL):
                if not monitoring_active:
                    break
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
            time.sleep(10)
    
    logger.info("🛑 Monitoring loop stopped")

@app.route('/')
def index():
    """Main page - redirect to status"""
    return redirect(url_for('status'))

@app.route('/status')
def status():
    """Status dashboard"""
    usernames = recorder.load_usernames()
    
    # Prepare user data
    user_data = []
    for username in usernames:
        user_info = {
            'username': username,
            'is_live': live_status.get(username, False),
            'is_recording': username in recording_processes,
            'last_check': last_check_times.get(username),
            'folder_exists': os.path.exists(os.path.join(RECORDINGS_DIR, username))
        }
        
        # Add recording details if active
        if username in recording_processes:
            rec_info = recording_processes[username]
            duration = datetime.now() - rec_info['start_time']
            filepath = rec_info['filepath']
            
            user_info.update({
                'recording_duration': str(duration).split('.')[0],
                'recording_file': rec_info['filename'],
                'file_size': os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                'recording_start_formatted': rec_info['start_time'].strftime('%H:%M:%S')
            })
        
        # Format last check time
        if user_info['last_check']:
            user_info['last_check_formatted'] = user_info['last_check'].strftime('%H:%M:%S')
        
        user_data.append(user_info)
    
    return render_template('status.html',
                         users=user_data,
                         monitoring_active=monitoring_active,
                         drive_connected=drive_service is not None,
                         total_recordings=len(recording_processes))

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user to monitoring"""
    username = request.form.get('username', '').strip()
    
    if username:
        success = recorder.add_username(username)
        if success:
            flash(f"✅ Added @{username} to monitoring", 'success')
        else:
            flash(f"⚠️ @{username} is already being monitored", 'warning')
    else:
        flash("❌ Please enter a valid username", 'error')
    
    return redirect(url_for('status'))

@app.route('/remove_user', methods=['POST'])
def remove_user():
    """Remove a user from monitoring"""
    username = request.form.get('username', '').strip()
    
    if username:
        success = recorder.remove_username(username)
        if success:
            flash(f"🗑️ Removed @{username} from monitoring", 'success')
        else:
            flash(f"❌ @{username} not found", 'error')
    
    return redirect(url_for('status'))

@app.route('/auth/google')
def auth_google():
    """Start Google OAuth flow"""
    try:
        # Load credentials from environment or file
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            # Use environment variable (for production)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(creds_json)
                credentials_file = f.name
        elif os.path.exists('credentials.json'):
            # Use local file (for development)
            credentials_file = 'credentials.json'
        else:
            flash("❌ Google OAuth credentials not configured", 'error')
            return redirect(url_for('status'))
        
        # Auto-detect redirect URI
        if request.headers.get('X-Forwarded-Proto'):
            scheme = request.headers.get('X-Forwarded-Proto')
        else:
            scheme = request.scheme
        
        host = request.headers.get('Host', request.host)
        redirect_uri = f"{scheme}://{host}/oauth2callback"
        
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        session['redirect_uri'] = redirect_uri
        
        logger.info(f"🔗 Starting OAuth flow with redirect: {redirect_uri}")
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"❌ OAuth error: {e}")
        flash(f"❌ OAuth setup error: {e}", 'error')
        return redirect(url_for('status'))

@app.route('/oauth2callback')
def oauth2callback():
    """Handle OAuth callback"""
    try:
        state = session.get('state')
        redirect_uri = session.get('redirect_uri')
        
        if not state or not redirect_uri:
            flash("❌ OAuth state error", 'error')
            return redirect(url_for('status'))
        
        # Load credentials from environment or file
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(creds_json)
                credentials_file = f.name
        else:
            credentials_file = 'credentials.json'
        
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'type': 'authorized_user'
        }
        
        # Setup Drive service
        setup_drive_service()
        
        # Create Drive folders for all existing users
        if drive_service:
            usernames = recorder.load_usernames()
            for username in usernames:
                recorder.create_user_folder(username)
                # Also create Drive folder structure
                try:
                    main_folder_id = recorder.get_or_create_folder(drive_service, "TikTok_Recordings")
                    user_folder_id = recorder.get_or_create_folder(drive_service, username, main_folder_id)
                    logger.info(f"📁 Created Drive folders for {username}")
                except Exception as e:
                    logger.error(f"❌ Error creating Drive folders for {username}: {e}")
        
        flash("✅ Google Drive authorized successfully!", 'success')
        logger.info("✅ Google Drive authorization completed")
        
        # Auto-start monitoring
        start_monitoring_internal()
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        flash(f"❌ Authorization failed: {e}", 'error')
    
    return redirect(url_for('status'))

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Start monitoring endpoint"""
    result = start_monitoring_internal()
    return jsonify(result)

def start_monitoring_internal():
    """Internal function to start monitoring"""
    global monitoring_active, monitoring_thread
    
    if monitoring_active:
        return {"status": "warning", "message": "Monitoring already active"}
    
    if not drive_service:
        return {"status": "error", "message": "Please authorize Google Drive first"}
    
    usernames = recorder.load_usernames()
    if not usernames:
        return {"status": "error", "message": "No usernames to monitor"}
    
    monitoring_active = True
    monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitoring_thread.start()
    
    logger.info("🚀 Monitoring started")
    return {"status": "success", "message": "Monitoring started successfully"}

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop monitoring"""
    global monitoring_active
    
    if not monitoring_active:
        return jsonify({"status": "warning", "message": "Monitoring not active"})
    
    monitoring_active = False
    
    # Stop all active recordings
    for username in list(recording_processes.keys()):
        recorder.stop_recording(username)
    
    logger.info("🛑 Monitoring stopped")
    return jsonify({"status": "success", "message": "Monitoring stopped"})

@app.route('/api/status')
def api_status():
    """API endpoint for status data"""
    usernames = recorder.load_usernames()
    
    status_data = {
        'monitoring_active': monitoring_active,
        'drive_connected': drive_service is not None,
        'total_users': len(usernames),
        'live_users': sum(1 for user in usernames if live_status.get(user, False)),
        'recording_users': len(recording_processes),
        'users': []
    }
    
    for username in usernames:
        user_info = {
            'username': username,
            'is_live': live_status.get(username, False),
            'is_recording': username in recording_processes,
            'last_check': last_check_times.get(username, datetime.now()).isoformat() if username in last_check_times else None
        }
        
        if username in recording_processes:
            rec_info = recording_processes[username]
            duration = datetime.now() - rec_info['start_time']
            filepath = rec_info['filepath']
            
            user_info.update({
                'recording_duration_seconds': int(duration.total_seconds()),
                'recording_file': rec_info['filename'],
                'file_size_bytes': os.path.getsize(filepath) if os.path.exists(filepath) else 0
            })
        
        status_data['users'].append(user_info)
    
    return jsonify(status_data)

@app.route('/api/usernames')
def api_usernames():
    """API endpoint for usernames count"""
    usernames = recorder.load_usernames()
    return jsonify({"count": len(usernames), "usernames": usernames})

@app.route('/revoke')
def revoke():
    """Revoke Google Drive authorization"""
    global drive_service
    
    if 'credentials' in session:
        del session['credentials']
        drive_service = None
        flash("🔓 Google Drive authorization revoked", 'info')
    
    return redirect(url_for('status'))

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global monitoring_active
    
    logger.info("🛑 Shutdown signal received")
    monitoring_active = False
    
    # Stop all recordings gracefully
    for username in list(recording_processes.keys()):
        recorder.stop_recording(username)
    
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    # Create initial folder structures
    usernames = recorder.load_usernames()
    logger.info(f"📋 Loaded {len(usernames)} usernames")
    
    for username in usernames:
        recorder.create_user_folder(username)
    
    # Setup Drive service if credentials exist
    setup_drive_service()
    
    # Get port from environment (Render sets this)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"🚀 Starting TikTok Livestream Recorder on port {port}")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)