#!/usr/bin/env python3
"""
Enhanced TikTok Livestream Recorder with 24/7 Continuous Recording
Designed for unlimited duration recording with 30-minute segments
"""

import os
import sys
import time
import logging
import subprocess
import threading
import signal
import psutil
import json
import yt_dlp
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests
from pathlib import Path
import shutil
import glob

# Enhanced logging configuration
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
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key-for-development')

# Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
SEGMENT_DURATION = 30  # 30 minutes per segment
MAX_RECORDING_DURATION = 24 * 60  # 24 hours max (in minutes)
CHECK_INTERVAL = 30  # Check every 30 seconds
RETRY_ATTEMPTS = 5

class LivestreamRecorder:
    """Enhanced livestream recorder with continuous recording capabilities"""
    
    def __init__(self):
        self.active_recordings = {}  # {username: RecordingSession}
        self.usernames = set()
        self.monitoring_active = False
        self.drive_service = None
        self.total_recordings = 0
        self.total_upload_size = 0
        
    def load_usernames(self):
        """Load usernames from file"""
        try:
            if os.path.exists('usernames.txt'):
                with open('usernames.txt', 'r', encoding='utf-8') as f:
                    usernames = set()
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Remove @ if present
                            username = line.lstrip('@')
                            if username:
                                usernames.add(username)
                    
                    self.usernames = usernames
                    logger.info(f"✅ Loaded {len(self.usernames)} usernames to monitor")
                    return True
            else:
                logger.warning("⚠️ usernames.txt not found")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error loading usernames: {e}")
            return False
    
    def check_livestream_status(self, username):
        """Check if user is currently live using yt-dlp"""
        try:
            # Use yt-dlp to check if user is live
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'socket_timeout': 30,
                'retries': 3,
            }
            
            url = f"https://www.tiktok.com/@{username}/live"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    
                    if info and info.get('is_live'):
                        stream_url = info.get('url') or info.get('manifest_url')
                        title = info.get('title', f"{username}_live")
                        
                        logger.info(f"✅ {username} is LIVE! Title: {title}")
                        return True, {
                            'stream_url': stream_url,
                            'title': title,
                            'uploader': info.get('uploader', username),
                            'duration': info.get('duration'),
                            'thumbnail': info.get('thumbnail')
                        }
                    else:
                        logger.info(f"❌ {username} is not live")
                        return False, None
                        
                except yt_dlp.DownloadError as e:
                    error_msg = str(e)
                    if "not currently live" in error_msg.lower():
                        logger.info(f"❌ {username} is not live")
                        return False, None
                    elif "captcha" in error_msg.lower():
                        logger.warning(f"🤖 {username} - Captcha challenge detected")
                        return False, None
                    else:
                        logger.error(f"❌ {username} - yt-dlp error: {error_msg}")
                        return False, None
                        
        except Exception as e:
            logger.error(f"❌ Error checking {username}: {e}")
            return False, None
    
    def start_recording_session(self, username, stream_info):
        """Start a new recording session with segmentation"""
        try:
            if username in self.active_recordings:
                logger.warning(f"⚠️ {username} already being recorded")
                return False
            
            # Create recording session
            session = RecordingSession(username, stream_info, self)
            self.active_recordings[username] = session
            
            # Start recording in separate thread
            session.start()
            
            logger.info(f"✅ Recording session started for {username}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start recording for {username}: {e}")
            return False
    
    def stop_recording_session(self, username):
        """Stop recording session"""
        try:
            if username in self.active_recordings:
                session = self.active_recordings[username]
                session.stop()
                del self.active_recordings[username]
                logger.info(f"🛑 Recording session stopped for {username}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error stopping recording for {username}: {e}")
            return False
    
    def monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("🔄 Starting monitoring loop...")
        self.monitoring_active = True
        
        while self.monitoring_active:
            try:
                cycle_start = time.time()
                
                # Reload usernames periodically
                self.load_usernames()
                
                if not self.usernames:
                    logger.warning("⚠️ No usernames to monitor")
                    time.sleep(60)
                    continue
                
                logger.info(f"🔍 Checking {len(self.usernames)} users...")
                
                for username in self.usernames.copy():
                    try:
                        # Check if user is live
                        is_live, stream_info = self.check_livestream_status(username)
                        
                        if is_live and username not in self.active_recordings:
                            logger.info(f"🔴 {username} is LIVE!")
                            self.start_recording_session(username, stream_info)
                        
                        elif not is_live and username in self.active_recordings:
                            logger.info(f"⭕ {username} went offline")
                            self.stop_recording_session(username)
                        
                        # Small delay between user checks
                        time.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing {username}: {e}")
                        continue
                
                # Log active recordings
                if self.active_recordings:
                    active_users = list(self.active_recordings.keys())
                    logger.info(f"🎬 Active recordings: {', '.join(active_users)}")
                
                # Calculate cycle time and wait
                cycle_time = time.time() - cycle_start
                wait_time = max(CHECK_INTERVAL - cycle_time, 5)
                logger.info(f"⏱️ Cycle completed in {cycle_time:.1f}s, waiting {wait_time:.1f}s...")
                
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
                time.sleep(60)  # Wait before retrying
    
    def start_monitoring(self):
        """Start monitoring in background thread"""
        if not self.monitoring_active:
            monitor_thread = threading.Thread(
                target=self.monitoring_loop,
                daemon=True,
                name="LivestreamMonitor"
            )
            monitor_thread.start()
            logger.info("✅ Monitoring started")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring_active = False
        
        # Stop all active recordings
        for username in list(self.active_recordings.keys()):
            self.stop_recording_session(username)
        
        logger.info("🛑 Monitoring stopped")
    
    def get_status(self):
        """Get current recorder status"""
        status = {
            'monitoring_active': self.monitoring_active,
            'total_usernames': len(self.usernames),
            'active_recordings': len(self.active_recordings),
            'usernames': list(self.usernames),
            'recordings': [],
            'total_recordings': self.total_recordings,
            'total_upload_size_mb': round(self.total_upload_size / (1024*1024), 2)
        }
        
        # Add active recording details
        for username, session in self.active_recordings.items():
            recording_info = {
                'username': username,
                'start_time': session.start_time.isoformat(),
                'current_segment': session.current_segment,
                'total_segments': len(session.completed_segments),
                'status': session.status,
                'duration_minutes': session.get_total_duration_minutes()
            }
            status['recordings'].append(recording_info)
        
        return status


class RecordingSession:
    """Individual recording session with 30-minute segmentation"""
    
    def __init__(self, username, stream_info, recorder):
        self.username = username
        self.stream_info = stream_info
        self.recorder = recorder
        self.start_time = datetime.now()
        self.current_segment = 1
        self.completed_segments = []
        self.current_process = None
        self.running = True
        self.status = "starting"
        self.drive_folder_id = None
        
        # Create output directory
        self.output_dir = Path(f"recordings/{username}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def start(self):
        """Start the recording session"""
        try:
            # Create Drive folder if service available
            if self.recorder.drive_service:
                self.drive_folder_id = self.create_drive_folder()
            
            # Start recording thread
            recording_thread = threading.Thread(
                target=self.recording_loop,
                daemon=True,
                name=f"Recording-{self.username}"
            )
            recording_thread.start()
            
            self.status = "recording"
            logger.info(f"✅ Recording thread started for {self.username}")
            
        except Exception as e:
            logger.error(f"❌ Failed to start recording session for {self.username}: {e}")
            self.status = "error"
    
    def recording_loop(self):
        """Main recording loop with 30-minute segments"""
        logger.info(f"🎬 Starting continuous recording for {self.username}")
        
        while self.running:
            try:
                # Check if user is still live before starting new segment
                is_live, updated_info = self.recorder.check_livestream_status(self.username)
                
                if not is_live:
                    logger.info(f"⭕ {self.username} went offline - ending recording")
                    break
                
                # Update stream info if available
                if updated_info:
                    self.stream_info.update(updated_info)
                
                # Start new segment
                segment_success = self.record_segment()
                
                if not segment_success:
                    logger.warning(f"⚠️ Segment failed for {self.username}, retrying...")
                    time.sleep(30)  # Wait before retry
                    continue
                
                # Brief pause between segments
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Recording loop error for {self.username}: {e}")
                time.sleep(30)
                
                # If too many errors, stop
                if not self.running:
                    break
        
        self.status = "completed"
        logger.info(f"✅ Recording session completed for {self.username}")
    
    def record_segment(self):
        """Record a single 30-minute segment"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.username}_{timestamp}_seg{self.current_segment:03d}.mp4"
            output_path = self.output_dir / filename
            
            logger.info(f"🎬 Starting segment {self.current_segment} for {self.username}")
            logger.info(f"📁 Output: {output_path}")
            
            # Enhanced yt-dlp options for continuous livestream recording
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': str(output_path),
                'live_from_start': True,
                'wait_for_video': (30, 90),  # Wait 30-90 seconds for video
                'fragment_retries': 10,
                'retries': 10,
                'socket_timeout': 60,
                'http_chunk_size': 10485760,  # 10MB chunks
                'hls_use_mpegts': True,
                'ignoreerrors': False,
                'no_warnings': False,
                'extract_flat': False,
                'writeinfojson': False,
                'writesubtitles': False,
                'writeautomaticsub': False,
            }
            
            # Use FFmpeg with enhanced options for livestream recording
            ffmpeg_opts = [
                '-c', 'copy',  # Copy streams without re-encoding
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts+igndts',
                '-t', str(SEGMENT_DURATION * 60),  # 30 minutes
                '-reconnect', '1',
                '-reconnect_at_eof', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '30',
                '-f', 'mp4',
                '-movflags', '+faststart'
            ]
            
            # Build yt-dlp command for direct ffmpeg usage
            stream_url = self.stream_info.get('stream_url')
            if not stream_url:
                # Extract stream URL using yt-dlp
                url = f"https://www.tiktok.com/@{self.username}/live"
                
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    stream_url = info.get('url') or info.get('manifest_url')
            
            if not stream_url:
                logger.error(f"❌ No stream URL found for {self.username}")
                return False
            
            # Build FFmpeg command for direct HLS recording
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts+igndts',
                '-t', str(SEGMENT_DURATION * 60),  # 30 minutes
                '-reconnect', '1',
                '-reconnect_at_eof', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '30',
                '-f', 'mp4',
                '-movflags', '+faststart',
                '-y',  # Overwrite output file
                str(output_path)
            ]
            
            logger.info(f"🎬 Starting FFmpeg recording for {self.username}")
            logger.debug(f"Command: {' '.join(ffmpeg_cmd)}")
            
            # Start FFmpeg process
            self.current_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                preexec_fn=os.setsid if os.name == 'posix' else None
            )
            
            # Monitor recording process
            segment_success = self.monitor_recording_process(output_path)
            
            if segment_success and output_path.exists() and output_path.stat().st_size > 1024:
                # Segment completed successfully
                file_size_mb = output_path.stat().st_size / (1024*1024)
                logger.info(f"✅ Segment {self.current_segment} completed: {file_size_mb:.1f}MB")
                
                # Add to completed segments
                segment_info = {
                    'segment': self.current_segment,
                    'filename': filename,
                    'path': str(output_path),
                    'size_mb': file_size_mb,
                    'start_time': datetime.now() - timedelta(minutes=SEGMENT_DURATION),
                    'end_time': datetime.now()
                }
                self.completed_segments.append(segment_info)
                
                # Upload to Drive if available
                if self.recorder.drive_service and self.drive_folder_id:
                    self.upload_segment_to_drive(segment_info)
                
                # Update counters
                self.current_segment += 1
                self.recorder.total_recordings += 1
                self.recorder.total_upload_size += output_path.stat().st_size
                
                return True
            else:
                logger.warning(f"⚠️ Segment {self.current_segment} failed or too small")
                # Clean up failed file
                if output_path.exists():
                    output_path.unlink()
                return False
                
        except Exception as e:
            logger.error(f"❌ Segment recording error for {self.username}: {e}")
            return False
    
    def monitor_recording_process(self, output_path):
        """Monitor the recording process with enhanced error handling"""
        try:
            start_time = time.time()
            last_size_check = 0
            no_growth_count = 0
            
            while self.current_process and self.current_process.poll() is None and self.running:
                # Check if we've reached segment duration
                elapsed = time.time() - start_time
                if elapsed >= (SEGMENT_DURATION * 60):
                    logger.info(f"⏰ Segment duration reached for {self.username}")
                    self.current_process.terminate()
                    break
                
                # Check file growth
                if output_path.exists():
                    current_size = output_path.stat().st_size
                    
                    if current_size == last_size_check:
                        no_growth_count += 1
                        if no_growth_count > 60:  # No growth for 2 minutes
                            logger.warning(f"⚠️ No file growth detected for {self.username}")
                            self.current_process.terminate()
                            break
                    else:
                        no_growth_count = 0
                        last_size_check = current_size
                        
                        # Log progress every 5 minutes
                        if int(elapsed) % 300 == 0:
                            size_mb = current_size / (1024*1024)
                            logger.info(f"📊 {self.username} - {elapsed/60:.1f}min, {size_mb:.1f}MB")
                
                time.sleep(2)  # Check every 2 seconds
            
            # Wait for process to finish
            if self.current_process:
                try:
                    self.current_process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ Force killing recording process for {self.username}")
                    if os.name == 'posix':
                        os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                    else:
                        self.current_process.kill()
                    self.current_process.wait()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Process monitoring error for {self.username}: {e}")
            return False
    
    def upload_segment_to_drive(self, segment_info):
        """Upload completed segment to Google Drive"""
        try:
            file_path = segment_info['path']
            filename = segment_info['filename']
            
            logger.info(f"☁️ Uploading {filename} to Drive...")
            
            file_metadata = {
                'name': filename,
                'parents': [self.drive_folder_id] if self.drive_folder_id else []
            }
            
            media = MediaFileUpload(
                file_path,
                mimetype='video/mp4',
                resumable=True,
                chunksize=10*1024*1024  # 10MB chunks
            )
            
            # Upload with retry logic
            for attempt in range(3):
                try:
                    file = self.recorder.drive_service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id,name,size'
                    ).execute()
                    
                    logger.info(f"✅ Uploaded {filename} to Drive (ID: {file.get('id')})")
                    
                    # Delete local file after successful upload
                    os.remove(file_path)
                    logger.info(f"🗑️ Deleted local file: {filename}")
                    
                    return True
                    
                except Exception as upload_error:
                    logger.warning(f"⚠️ Upload attempt {attempt + 1} failed: {upload_error}")
                    if attempt < 2:
                        time.sleep(30 * (attempt + 1))  # Progressive delay
                    else:
                        raise upload_error
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Upload error for {filename}: {e}")
            return False
    
    def create_drive_folder(self):
        """Create Google Drive folder for user"""
        try:
            folder_name = f"TikTok_Live_{self.username}_{datetime.now().strftime('%Y%m%d')}"
            
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.recorder.drive_service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"☁️ Created Drive folder for {self.username}: {folder_name}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"❌ Failed to create Drive folder for {self.username}: {e}")
            return None
    
    def stop(self):
        """Stop the recording session"""
        self.running = False
        
        if self.current_process:
            try:
                logger.info(f"🛑 Stopping recording for {self.username}")
                
                # Graceful termination
                self.current_process.terminate()
                
                try:
                    self.current_process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    if os.name == 'posix':
                        os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                    else:
                        self.current_process.kill()
                    self.current_process.wait()
                
                logger.info(f"✅ Recording stopped for {self.username}")
                
            except Exception as e:
                logger.error(f"❌ Error stopping recording for {self.username}: {e}")
        
        self.status = "stopped"
    
    def get_total_duration_minutes(self):
        """Get total recording duration in minutes"""
        elapsed = datetime.now() - self.start_time
        return int(elapsed.total_seconds() / 60)


# Global recorder instance
recorder = LivestreamRecorder()

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/status')
def status():
    """Status API endpoint"""
    return jsonify(recorder.get_status())

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': recorder.monitoring_active,
        'active_recordings': len(recorder.active_recordings),
        'uptime_minutes': int((datetime.now() - start_time).total_seconds() / 60)
    })

@app.route('/start_monitoring')
def start_monitoring():
    """Start monitoring endpoint"""
    recorder.start_monitoring()
    return jsonify({'status': 'started', 'message': 'Monitoring started'})

@app.route('/stop_monitoring')
def stop_monitoring():
    """Stop monitoring endpoint"""
    recorder.stop_monitoring()
    return jsonify({'status': 'stopped', 'message': 'Monitoring stopped'})

@app.route('/auth/google')
def auth_google():
    """Start Google OAuth flow"""
    try:
        # Load credentials
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            creds_dict = json.loads(creds_json)
            with open('temp_credentials.json', 'w') as f:
                json.dump(creds_dict, f)
            creds_file = 'temp_credentials.json'
        else:
            creds_file = 'credentials.json'
        
        if not os.path.exists(creds_file):
            return jsonify({'error': 'Google credentials not found'}), 400
        
        # Get redirect URI
        redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
        if not redirect_uri:
            redirect_uri = request.url_root.rstrip('/') + '/oauth2callback'
        
        # Create OAuth flow
        flow = Flow.from_client_secrets_file(
            creds_file,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        
        # Clean up temp file
        if creds_file == 'temp_credentials.json':
            os.remove(creds_file)
        
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"❌ Google auth error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/oauth2callback')
def oauth2callback():
    """Handle OAuth callback"""
    try:
        state = session.get('state')
        if not state or request.args.get('state') != state:
            return jsonify({'error': 'Invalid state parameter'}), 400
        
        # Load credentials again
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            creds_dict = json.loads(creds_json)
            with open('temp_credentials.json', 'w') as f:
                json.dump(creds_dict, f)
            creds_file = 'temp_credentials.json'
        else:
            creds_file = 'credentials.json'
        
        redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
        if not redirect_uri:
            redirect_uri = request.url_root.rstrip('/') + '/oauth2callback'
        
        flow = Flow.from_client_secrets_file(
            creds_file,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
            state=state
        )
        
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        
        # Save credentials to environment or file
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Save to file
        with open('token.json', 'w') as f:
            json.dump(creds_data, f)
        
        # Initialize Drive service
        recorder.drive_service = build('drive', 'v3', credentials=credentials)
        
        # Clean up temp file
        if creds_file == 'temp_credentials.json':
            os.remove(creds_file)
        
        logger.info("✅ Google Drive authorization successful")
        
        return '''
        <html>
        <body>
        <h2>✅ Authorization Successful!</h2>
        <p>Google Drive has been authorized successfully.</p>
        <p>You can now close this window and return to the main dashboard.</p>
        <script>setTimeout(() => window.close(), 3000);</script>
        </body>
        </html>
        '''
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        return jsonify({'error': str(e)}), 500

def load_google_credentials():
    """Load existing Google credentials"""
    try:
        if os.path.exists('token.json'):
            with open('token.json', 'r') as f:
                creds_data = json.load(f)
            
            credentials = Credentials(
                token=creds_data['token'],
                refresh_token=creds_data.get('refresh_token'),
                token_uri=creds_data['token_uri'],
                client_id=creds_data['client_id'],
                client_secret=creds_data['client_secret'],
                scopes=creds_data['scopes']
            )
            
            # Refresh if needed
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                
                # Save refreshed token
                updated_creds = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                
                with open('token.json', 'w') as f:
                    json.dump(updated_creds, f)
            
            # Initialize Drive service
            recorder.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("✅ Google Drive service initialized")
            return True
            
    except Exception as e:
        logger.warning(f"⚠️ Could not load Google credentials: {e}")
        logger.info("💡 Visit /auth/google to authorize Google Drive")
        return False

def create_template_files():
    """Create HTML template files"""
    try:
        template_dir = Path('templates')
        template_dir.mkdir(exist_ok=True)
        
        # Create index.html template
        index_html = '''<!DOCTYPE html>
<html>
<head>
    <title>TikTok Livestream Recorder</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
        .status-card { background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; }
        .recording-card { border-left-color: #28a745; }
        .offline-card { border-left-color: #6c757d; }
        .error-card { border-left-color: #dc3545; }
        .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
        .btn:hover { background: #0056b3; }
        .btn-success { background: #28a745; }
        .btn-danger { background: #dc3545; }
        .live-indicator { display: inline-block; width: 10px; height: 10px; background: #ff0000; border-radius: 50%; margin-right: 5px; animation: pulse 1s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .stats { display: flex; justify-content: space-around; margin: 20px 0; }
        .stat { text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #007bff; }
        .recordings-list { max-height: 400px; overflow-y: auto; }
        .recording-item { background: #e8f5e8; padding: 10px; margin: 5px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 TikTok Livestream Recorder</h1>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-number" id="totalUsers">-</div>
                <div>Total Users</div>
            </div>
            <div class="stat">
                <div class="stat-number" id="activeRecordings">-</div>
                <div>Active Recordings</div>
            </div>
            <div class="stat">
                <div class="stat-number" id="totalRecordings">-</div>
                <div>Total Recordings</div>
            </div>
            <div class="stat">
                <div class="stat-number" id="uploadSize">-</div>
                <div>Upload Size (MB)</div>
            </div>
        </div>
        
        <div style="text-align: center; margin: 20px 0;">
            <button class="btn btn-success" onclick="startMonitoring()">▶️ Start Monitoring</button>
            <button class="btn btn-danger" onclick="stopMonitoring()">⏹️ Stop Monitoring</button>
            <button class="btn" onclick="refreshStatus()">🔄 Refresh</button>
            <a href="/auth/google" class="btn">🔗 Authorize Google Drive</a>
        </div>
        
        <div id="statusContainer">
            <p>Loading status...</p>
        </div>
    </div>

    <script>
        function refreshStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    updateDashboard(data);
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('statusContainer').innerHTML = '<p style="color: red;">Error loading status</p>';
                });
        }
        
        function updateDashboard(data) {
            // Update stats
            document.getElementById('totalUsers').textContent = data.total_usernames;
            document.getElementById('activeRecordings').textContent = data.active_recordings;
            document.getElementById('totalRecordings').textContent = data.total_recordings;
            document.getElementById('uploadSize').textContent = data.total_upload_size_mb;
            
            // Update status container
            let html = '<h3>📊 Current Status</h3>';
            
            if (data.monitoring_active) {
                html += '<p style="color: green;">✅ Monitoring is ACTIVE</p>';
            } else {
                html += '<p style="color: red;">❌ Monitoring is STOPPED</p>';
            }
            
            // Show usernames
            html += '<h4>👥 Monitored Users</h4>';
            html += '<div class="status-grid">';
            
            data.usernames.forEach(username => {
                const recording = data.recordings.find(r => r.username === username);
                
                if (recording) {
                    html += `
                        <div class="status-card recording-card">
                            <h5><span class="live-indicator"></span>${username}</h5>
                            <p><strong>🔴 LIVE & RECORDING</strong></p>
                            <p>Segment: ${recording.current_segment}</p>
                            <p>Duration: ${recording.duration_minutes} minutes</p>
                            <p>Total Segments: ${recording.total_segments}</p>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="status-card offline-card">
                            <h5>${username}</h5>
                            <p>⭕ Offline</p>
                        </div>
                    `;
                }
            });
            
            html += '</div>';
            
            // Show active recordings details
            if (data.recordings.length > 0) {
                html += '<h4>🎬 Active Recordings</h4>';
                html += '<div class="recordings-list">';
                
                data.recordings.forEach(recording => {
                    html += `
                        <div class="recording-item">
                            <strong>${recording.username}</strong> - 
                            Segment ${recording.current_segment} (${recording.duration_minutes} min) - 
                            ${recording.total_segments} completed segments
                        </div>
                    `;
                });
                
                html += '</div>';
            }
            
            document.getElementById('statusContainer').innerHTML = html;
        }
        
        function startMonitoring() {
            fetch('/start_monitoring')
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    refreshStatus();
                });
        }
        
        function stopMonitoring() {
            fetch('/stop_monitoring')
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    refreshStatus();
                });
        }
        
        // Auto-refresh every 30 seconds
        setInterval(refreshStatus, 30000);
        
        // Initial load
        refreshStatus();
    </script>
</body>
</html>'''
        
        with open(template_dir / 'index.html', 'w') as f:
            f.write(index_html)
        
        logger.info("✅ Template files created")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creating templates: {e}")
        return False

def cleanup_old_recordings():
    """Clean up old recordings to save disk space"""
    try:
        recordings_dir = Path('recordings')
        if not recordings_dir.exists():
            return
        
        # Find files older than 1 hour (should be uploaded by then)
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        for file_path in recordings_dir.rglob('*.mp4'):
            if file_path.stat().st_mtime < cutoff_time.timestamp():
                try:
                    file_size_mb = file_path.stat().st_size / (1024*1024)
                    file_path.unlink()
                    logger.info(f"🗑️ Cleaned up old recording: {file_path.name} ({file_size_mb:.1f}MB)")
                except Exception as e:
                    logger.warning(f"⚠️ Could not delete {file_path}: {e}")
    
    except Exception as e:
        logger.error(f"❌ Cleanup error: {e}")

def setup_cleanup_scheduler():
    """Setup automatic cleanup of old files"""
    def cleanup_loop():
        while True:
            try:
                time.sleep(3600)  # Run every hour
                cleanup_old_recordings()
            except Exception as e:
                logger.error(f"❌ Cleanup loop error: {e}")
                time.sleep(300)  # Wait 5 minutes before retry
    
    cleanup_thread = threading.Thread(
        target=cleanup_loop,
        daemon=True,
        name="CleanupScheduler"
    )
    cleanup_thread.start()
    logger.info("✅ Cleanup scheduler started")

def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logger.info("🛑 Received shutdown signal")
    recorder.stop_monitoring()
    sys.exit(0)

# Global variables
start_time = datetime.now()

if __name__ == '__main__':
    logger.info("🚀 TikTok Livestream Recorder Starting...")
    logger.info("=" * 60)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create necessary directories
        os.makedirs('recordings', exist_ok=True)
        os.makedirs('templates', exist_ok=True)
        
        # Create template files
        create_template_files()
        
        # Load usernames
        recorder.load_usernames()
        
        # Try to load Google credentials
        load_google_credentials()
        
        # Setup cleanup scheduler
        setup_cleanup_scheduler()
        
        # Auto-start monitoring if usernames exist
        if recorder.usernames:
            logger.info("🎯 Auto-starting monitoring...")
            recorder.start_monitoring()
        
        # Get port from environment
        port = int(os.environ.get('PORT', 5000))
        
        logger.info(f"🌐 Starting Flask server on port {port}")
        logger.info(f"📱 Dashboard: http://localhost:{port}")
        logger.info("=" * 60)
        
        # Start Flask app
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False
        )
        
    except Exception as e:
        logger.error(f"❌ Application startup failed: {e}")
        sys.exit(1)
