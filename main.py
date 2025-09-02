#!/usr/bin/env python3
"""
TikTok Livestream Recorder - PRODUCTION FIXED VERSION
Automatically monitors TikTok users and records their livestreams with 24/7 reliability
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
import random
import urllib.parse
import gc
import traceback
from threading import Lock

# Flask app configuration
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
RECORDINGS_DIR = "recordings"
USERNAMES_FILE = "usernames.txt"
CHECK_INTERVAL = 45  # Increased to reduce API load
RECORDING_QUALITY = "best[height<=480]/worst[height<=480]/best"
MAX_RECORDING_DURATION = 4 * 3600  # 4 hours max per recording

# Global state with thread safety
monitoring_active = False
monitoring_thread = None
recording_processes = {}
live_status = {}
last_check_times = {}
drive_service = None
active_recordings_lock = Lock()
service_lock = Lock()

# Session management
session_start_time = datetime.now()
last_service_refresh = datetime.now()
error_count = 0
MAX_ERRORS_BEFORE_RESET = 10

# Setup enhanced logging
class RotatingHandler(logging.Handler):
    def __init__(self, max_size=10*1024*1024):  # 10MB max
        super().__init__()
        self.max_size = max_size
        
    def emit(self, record):
        try:
            if os.path.exists('app.log') and os.path.getsize('app.log') > self.max_size:
                # Rotate log file
                if os.path.exists('app.log.old'):
                    os.remove('app.log.old')
                os.rename('app.log', 'app.log.old')
        except:
            pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(),
        RotatingHandler()
    ]
)
logger = logging.getLogger(__name__)

class TikTokLiveDetector:
    """Enhanced TikTok live detection with better reliability and error recovery"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 15
        self.user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Android 12; Mobile; rv:68.0) Gecko/68.0 Firefox/102.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        ]
        self.last_user_agent_rotation = datetime.now()
        self.current_ua_index = 0
    
    def rotate_user_agent(self):
        """Rotate user agent every 5 minutes"""
        if datetime.now() - self.last_user_agent_rotation > timedelta(minutes=5):
            self.current_ua_index = (self.current_ua_index + 1) % len(self.user_agents)
            self.last_user_agent_rotation = datetime.now()
    
    def get_headers(self, mobile=True):
        """Get current headers with rotation"""
        self.rotate_user_agent()
        ua = self.user_agents[self.current_ua_index]
        
        return {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
    
    def check_live_with_ytdlp(self, username):
        """Enhanced yt-dlp check with better error handling"""
        try:
            clean_username = username.replace('@', '').strip()
            live_url = f"https://www.tiktok.com/@{clean_username}/live"
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'timeout': 20,
                'socket_timeout': 15,
                'http_headers': self.get_headers(mobile=True),
                'retries': 2,
                'fragment_retries': 2,
                'extractor_retries': 2
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(live_url, download=False)
                    if info and (info.get('url') or info.get('formats')):
                        # Validate that we actually have a playable stream
                        if self._validate_stream_info(info):
                            logger.info(f"✅ yt-dlp: {username} is LIVE with valid stream!")
                            return True, info
                        else:
                            logger.warning(f"⚠️ yt-dlp: {username} detected but no valid stream")
                            return False, None
                            
                except yt_dlp.utils.DownloadError as e:
                    error_msg = str(e).lower()
                    if any(phrase in error_msg for phrase in ["not currently live", "private", "unavailable", "removed"]):
                        return False, None
                    elif "geo" in error_msg or "region" in error_msg:
                        logger.warning(f"⚠️ Geo-blocked for {username}")
                        return False, None
                    else:
                        logger.error(f"❌ yt-dlp error for {username}: {e}")
                        return False, None
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ yt-dlp check failed for {username}: {e}")
            return False, None
    
    def _validate_stream_info(self, info):
        """Validate that stream info contains usable data"""
        if not info:
            return False
            
        # Check for direct URL
        if info.get('url'):
            return True
            
        # Check formats
        formats = info.get('formats', [])
        if not formats:
            return False
            
        # Look for valid formats with URLs
        valid_formats = [f for f in formats if f.get('url') and f.get('protocol') != 'unknown']
        return len(valid_formats) > 0
    
    def check_live_status(self, username):
        """Main live detection method with enhanced reliability"""
        try:
            clean_username = username.replace('@', '').strip()
            
            # Primary method: yt-dlp
            logger.debug(f"🔍 Checking {username} with yt-dlp...")
            is_live_ytdlp, stream_info = self.check_live_with_ytdlp(username)
            
            if is_live_ytdlp and stream_info:
                return True, stream_info
            
            # If yt-dlp fails, wait and try once more
            if not is_live_ytdlp:
                time.sleep(3)  # Brief delay
                logger.debug(f"🔍 Retry check for {username}...")
                is_live_retry, stream_info_retry = self.check_live_with_ytdlp(username)
                if is_live_retry and stream_info_retry:
                    return True, stream_info_retry
            
            logger.info(f"❌ {username} is not live")
            return False, None
            
        except Exception as e:
            logger.error(f"❌ Live detection error for {username}: {e}")
            return False, None

class StreamRecorder:
    def __init__(self):
        self.live_detector = TikTokLiveDetector()
        self.recording_files = {}  # Track active recording files to prevent duplicates
        self.upload_queue = []
        self.upload_lock = Lock()
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
        
        # Also create Google Drive folder if service is available
        if drive_service:
            try:
                main_folder_id = self.get_or_create_folder(drive_service, "TikTok_Recordings")
                if main_folder_id:
                    user_folder_id = self.get_or_create_folder(drive_service, username, main_folder_id)
                    if user_folder_id:
                        logger.info(f"☁️ Created Drive folder for {username}")
            except Exception as e:
                logger.error(f"❌ Error creating Drive folder for {username}: {e}")
    
    def check_live_status(self, username):
        """Check if user is live using enhanced detection"""
        return self.live_detector.check_live_status(username)
    
    def get_unique_filename(self, username):
        """Generate unique filename to prevent duplicates"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"{username}_{timestamp}"
        
        # Check for existing files in the same minute
        user_dir = os.path.join(RECORDINGS_DIR, username)
        counter = 1
        while True:
            if counter == 1:
                filename = f"{base_filename}.mp4"
            else:
                filename = f"{base_filename}_{counter}.mp4"
            
            filepath = os.path.join(user_dir, filename)
            
            # Check if file exists or is being recorded
            if not os.path.exists(filepath) and filename not in self.recording_files.values():
                self.recording_files[username] = filename
                return filename, filepath
            
            counter += 1
            if counter > 100:  # Safety limit
                break
        
        # Fallback with microseconds
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"{username}_{timestamp}.mp4"
        filepath = os.path.join(user_dir, filename)
        self.recording_files[username] = filename
        return filename, filepath
    
    def start_recording(self, username, stream_info=None):
        """Start recording with enhanced FFmpeg settings and duplicate prevention"""
        with active_recordings_lock:
            if username in recording_processes:
                # Check if existing process is still alive
                existing_process = recording_processes[username]['process']
                if existing_process.poll() is None:
                    logger.info(f"📹 Already recording {username} (active process)")
                    return False
                else:
                    # Clean up dead process
                    logger.warning(f"🧹 Cleaning up dead recording process for {username}")
                    del recording_processes[username]
                    if username in self.recording_files:
                        del self.recording_files[username]
        
        try:
            # Ensure user folder exists
            self.create_user_folder(username)
            
            # Get stream URL using yt-dlp if not provided
            if not stream_info:
                logger.info(f"🔗 Getting stream URL for {username}...")
                is_live, stream_info = self.live_detector.check_live_with_ytdlp(username)
                if not is_live or not stream_info:
                    logger.error(f"❌ Cannot get stream info for {username}")
                    return False
            
            # Extract best quality stream URL (480p max)
            stream_url = self._extract_best_stream_url(stream_info)
            if not stream_url:
                logger.error(f"❌ No valid stream URL found for {username}")
                return False
            
            # Generate unique filename
            filename, filepath = self.get_unique_filename(username)
            
            logger.info(f"🎬 Starting recording for {username}")
            logger.info(f"📁 Output: {filepath}")
            logger.info(f"🔗 Stream URL: {stream_url[:100]}...")
            
            # Enhanced FFmpeg command for reliable recording with better compatibility
            cmd = [
                'ffmpeg',
                '-headers', f'User-Agent: {self.live_detector.user_agents[0]}',
                '-headers', 'Referer: https://www.tiktok.com/',
                '-i', stream_url,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'medium',           # Better quality
                '-crf', '26',                  # Better quality for 480p
                '-maxrate', '1500k',           # Increased bitrate
                '-bufsize', '3000k',           # Larger buffer
                '-vf', 'scale=-2:480:flags=lanczos',  # Better scaling
                '-movflags', '+faststart+frag_keyframe+empty_moov',  # Better streaming compatibility
                '-f', 'mp4',                   # Ensure MP4 format
                '-avoid_negative_ts', 'make_zero',  # Fix timestamp issues
                '-fflags', '+genpts',          # Generate presentation timestamps
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '15',
                '-rw_timeout', '20000000',     # 20 second timeout
                '-analyzeduration', '10000000', # 10 seconds analysis
                '-probesize', '10000000',      # 10MB probe size
                '-thread_queue_size', '512',   # Larger thread queue
                '-y',                          # Overwrite output file
                filepath
            ]
            
            # Start FFmpeg process with better settings
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None  # Create process group
            )
            
            # Store recording info
            with active_recordings_lock:
                recording_processes[username] = {
                    'process': process,
                    'filename': filename,
                    'filepath': filepath,
                    'start_time': datetime.now(),
                    'stream_url': stream_url,
                    'stream_info': stream_info,
                    'last_size_check': 0,
                    'stall_count': 0
                }
            
            logger.info(f"✅ Recording started for {username} (PID: {process.pid})")
            
            # Start monitoring thread for this recording
            monitor_thread = threading.Thread(
                target=self.monitor_recording,
                args=(username,),
                daemon=True,
                name=f"RecordingMonitor-{username}"
            )
            monitor_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error starting recording for {username}: {e}")
            logger.error(traceback.format_exc())
            # Clean up if failed
            with active_recordings_lock:
                if username in recording_processes:
                    del recording_processes[username]
                if username in self.recording_files:
                    del self.recording_files[username]
            return False
    
    def _extract_best_stream_url(self, stream_info):
        """Extract the best stream URL from yt-dlp info"""
        if not stream_info:
            return None
            
        # Direct URL
        if stream_info.get('url'):
            return stream_info['url']
        
        # From formats
        formats = stream_info.get('formats', [])
        if not formats:
            return None
        
        # Filter and sort formats
        valid_formats = []
        for fmt in formats:
            if not fmt.get('url'):
                continue
                
            height = fmt.get('height', 0)
            width = fmt.get('width', 0)
            fps = fmt.get('fps', 0)
            
            # Prefer formats under 480p with reasonable fps
            if height <= 480 and fps <= 60:
                valid_formats.append(fmt)
        
        if not valid_formats:
            # Fallback to any format with URL
            valid_formats = [f for f in formats if f.get('url')]
        
        if not valid_formats:
            return None
        
        # Sort by quality (prefer higher quality within limits)
        valid_formats.sort(key=lambda f: (f.get('height', 0), f.get('fps', 0)), reverse=True)
        
        return valid_formats[0]['url']
    
    def monitor_recording(self, username):
        """Enhanced recording monitoring with better stall detection"""
        try:
            if username not in recording_processes:
                return
            
            process_info = recording_processes[username]
            process = process_info['process']
            filepath = process_info['filepath']
            start_time = process_info['start_time']
            
            logger.info(f"👁️ Monitoring recording for {username}")
            
            last_size = 0
            stall_count = 0
            last_log_time = datetime.now()
            
            while process.poll() is None:
                try:
                    # Check recording duration limit
                    duration = datetime.now() - start_time
                    if duration.total_seconds() > MAX_RECORDING_DURATION:
                        logger.info(f"⏰ Recording duration limit reached for {username}")
                        process.terminate()
                        break
                    
                    # Check if file exists and is growing
                    if os.path.exists(filepath):
                        current_size = os.path.getsize(filepath)
                        
                        # Check for file growth
                        if current_size > last_size:
                            stall_count = 0
                            process_info['last_size_check'] = current_size
                            
                            # Log progress every 2 minutes
                            if datetime.now() - last_log_time > timedelta(minutes=2):
                                logger.info(f"📊 {username}: {duration.total_seconds():.0f}s, {current_size/1024/1024:.1f}MB")
                                last_log_time = datetime.now()
                        else:
                            stall_count += 1
                            if stall_count > 8:  # 80 seconds without growth
                                logger.warning(f"⚠️ Recording stalled for {username}, stopping...")
                                process.terminate()
                                break
                        
                        last_size = current_size
                    else:
                        logger.warning(f"⚠️ Recording file not found: {filepath}")
                        stall_count += 1
                        if stall_count > 5:
                            break
                    
                    time.sleep(10)  # Check every 10 seconds
                    
                except Exception as e:
                    logger.error(f"❌ Error in recording monitor for {username}: {e}")
                    break
            
            # Process ended - handle cleanup
            self._handle_recording_completion(username)
                
        except Exception as e:
            logger.error(f"❌ Error monitoring recording for {username}: {e}")
            self._cleanup_recording(username)
    
    def _handle_recording_completion(self, username):
        """Handle recording completion and upload"""
        try:
            if username not in recording_processes:
                return
            
            process_info = recording_processes[username]
            process = process_info['process']
            filepath = process_info['filepath']
            start_time = process_info['start_time']
            
            return_code = process.returncode
            duration = datetime.now() - start_time
            
            if return_code == 0:
                logger.info(f"✅ Recording completed for {username} ({duration.total_seconds():.0f}s)")
            else:
                logger.warning(f"⚠️ Recording ended with code {return_code} for {username}")
            
            # Check final file
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                if file_size > 100000:  # At least 100KB
                    logger.info(f"💾 Recording saved: {filepath} ({file_size/1024/1024:.1f}MB)")
                    
                    # Add to upload queue
                    with self.upload_lock:
                        self.upload_queue.append({
                            'filepath': filepath,
                            'username': username,
                            'timestamp': datetime.now()
                        })
                    
                    # Start upload thread if not already running
                    threading.Thread(
                        target=self._process_upload_queue,
                        daemon=True,
                        name="UploadProcessor"
                    ).start()
                else:
                    logger.warning(f"⚠️ Recording file too small: {filepath} ({file_size} bytes)")
                    try:
                        os.remove(filepath)
                        logger.info(f"🗑️ Removed small file: {filepath}")
                    except:
                        pass
            
            # Clean up
            self._cleanup_recording(username)
                
        except Exception as e:
            logger.error(f"❌ Error handling recording completion for {username}: {e}")
            self._cleanup_recording(username)
    
    def _cleanup_recording(self, username):
        """Clean up recording process data"""
        with active_recordings_lock:
            if username in recording_processes:
                del recording_processes[username]
            if username in self.recording_files:
                del self.recording_files[username]
        logger.info(f"🧹 Cleaned up recording process for {username}")
    
    def stop_recording(self, username):
        """Stop recording for a user"""
        with active_recordings_lock:
            if username not in recording_processes:
                return False
        
        try:
            process = recording_processes[username]['process']
            
            # Send SIGTERM for graceful shutdown
            try:
                if hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
            except:
                process.terminate()
            
            # Wait for graceful termination
            try:
                process.wait(timeout=20)
                logger.info(f"🛑 Gracefully stopped recording for {username}")
            except subprocess.TimeoutExpired:
                # Force kill if needed
                try:
                    if hasattr(os, 'killpg'):
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
                except:
                    pass
                logger.warning(f"🔪 Force killed recording for {username}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error stopping recording for {username}: {e}")
            return False
    
    def _process_upload_queue(self):
        """Process upload queue with retry logic"""
        while True:
            with self.upload_lock:
                if not self.upload_queue:
                    break
                
                upload_item = self.upload_queue.pop(0)
            
            # Try upload with retries
            for attempt in range(3):
                try:
                    success = self.upload_to_drive(
                        upload_item['filepath'],
                        upload_item['username']
                    )
                    if success:
                        break
                    else:
                        if attempt < 2:
                            time.sleep(30 * (attempt + 1))  # Exponential backoff
                        
                except Exception as e:
                    logger.error(f"❌ Upload attempt {attempt + 1} failed: {e}")
                    if attempt < 2:
                        time.sleep(30 * (attempt + 1))
    
    def upload_to_drive(self, filepath, username):
        """Enhanced Drive upload with better error handling"""
        try:
            if not drive_service:
                logger.warning("❌ Google Drive not connected")
                return False
            
            if not os.path.exists(filepath):
                logger.error(f"❌ File not found for upload: {filepath}")
                return False
            
            logger.info(f"☁️ Starting Drive upload for {username}...")
            
            # Create folder structure: TikTok_Recordings/Username/YYYY-MM/
            current_date = datetime.now()
            year_month = current_date.strftime('%Y-%m')
            
            # Get or create folders
            main_folder_id = self.get_or_create_folder(drive_service, "TikTok_Recordings")
            if not main_folder_id:
                logger.error(f"❌ Cannot create main Drive folder")
                return False
            
            user_folder_id = self.get_or_create_folder(drive_service, username, main_folder_id)
            if not user_folder_id:
                logger.error(f"❌ Cannot create user Drive folder")
                return False
            
            date_folder_id = self.get_or_create_folder(drive_service, year_month, user_folder_id)
            if not date_folder_id:
                logger.error(f"❌ Cannot create date Drive folder")
                return False
            
            # Check if file already exists in Drive
            filename = os.path.basename(filepath)
            existing_files = drive_service.files().list(
                q=f"name='{filename}' and '{date_folder_id}' in parents and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            if existing_files.get('files'):
                logger.info(f"⚠️ File already exists in Drive: {filename}")
                # Remove local file since it's already uploaded
                try:
                    os.remove(filepath)
                    logger.info(f"🗑️ Removed duplicate local file: {filepath}")
                except:
                    pass
                return True
            
            # Upload file with resumable upload
            file_metadata = {
                'name': filename,
                'parents': [date_folder_id],
                'description': f'TikTok livestream recording of @{username} from {current_date.strftime("%Y-%m-%d %H:%M:%S")}'
            }
            
            media = MediaFileUpload(
                filepath, 
                resumable=True,
                chunksize=1024*1024*5  # 5MB chunks
            )
            
            # Execute upload with timeout
            request = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink,size'
            )
            
            file = None
            response = None
            
            # Resumable upload loop
            while response is None:
                try:
                    status, response = request.next_chunk()
                    if status:
                        logger.info(f"☁️ Upload progress for {username}: {int(status.progress() * 100)}%")
                except Exception as chunk_error:
                    logger.error(f"❌ Upload chunk error: {chunk_error}")
                    raise chunk_error
            
            file = response
            file_id = file.get('id')
            web_link = file.get('webViewLink')
            file_size = file.get('size', '0')
            
            logger.info(f"✅ Uploaded to Drive: {filename} (ID: {file_id}, Size: {int(file_size)/1024/1024:.1f}MB)")
            
            # Remove local file after successful upload
            try:
                os.remove(filepath)
                logger.info(f"🗑️ Removed local file: {filepath}")
            except Exception as e:
                logger.warning(f"⚠️ Could not remove local file: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Drive upload failed for {username}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def get_or_create_folder(self, service, folder_name, parent_id=None):
        """Get or create a folder in Google Drive with retry logic"""
        try:
            # Search for existing folder with retry
            for attempt in range(3):
                try:
                    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                    if parent_id:
                        query += f" and '{parent_id}' in parents"
                    
                    results = service.files().list(
                        q=query,
                        fields="files(id, name)",
                        pageSize=10
                    ).execute()
                    
                    folders = results.get('files', [])
                    
                    if folders:
                        return folders[0]['id']
                    
                    # Create new folder if not found
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
                    if attempt < 2:
                        logger.warning(f"⚠️ Folder operation retry {attempt + 1}: {e}")
                        time.sleep(5)
                        continue
                    else:
                        raise e
                
        except Exception as e:
            logger.error(f"❌ Error with Drive folder {folder_name}: {e}")
            return None

# Initialize recorder
recorder = StreamRecorder()

def setup_drive_service():
    """Enhanced Drive service setup with better error handling"""
    global drive_service, error_count, last_service_refresh
    
    with service_lock:
        try:
            if 'credentials' not in session:
                logger.warning("❌ No credentials in session")
                return False
            
            creds_data = session['credentials']
            creds = Credentials.from_authorized_user_info(creds_data)
            
            # Refresh if needed
            if creds.expired and creds.refresh_token:
                logger.info("🔄 Refreshing Google credentials...")
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
                session.permanent = True  # Make session permanent
            
            # Build service with retry logic
            for attempt in range(3):
                try:
                    drive_service = build('drive', 'v3', credentials=creds)
                    
                    # Test the service
                    test_query = drive_service.files().list(pageSize=1).execute()
                    
                    logger.info("✅ Google Drive service initialized and tested")
                    last_service_refresh = datetime.now()
                    error_count = 0
                    return True
                    
                except Exception as e:
                    if attempt < 2:
                        logger.warning(f"⚠️ Drive service setup retry {attempt + 1}: {e}")
                        time.sleep(5)
                        continue
                    else:
                        raise e
            
        except Exception as e:
            logger.error(f"❌ Error setting up Drive service: {e}")
            drive_service = None
            error_count += 1
            
            # Reset session if too many errors
            if error_count > MAX_ERRORS_BEFORE_RESET:
                logger.warning("🔄 Too many errors, clearing session...")
                session.clear()
                error_count = 0
            
        return False

def refresh_drive_service():
    """Periodically refresh Drive service to prevent timeouts"""
    global last_service_refresh
    
    if drive_service and datetime.now() - last_service_refresh > timedelta(hours=1):
        logger.info("🔄 Refreshing Drive service...")
        setup_drive_service()

def monitoring_loop():
    """Enhanced monitoring loop with better error recovery and 24/7 reliability"""
    global monitoring_active, error_count
    
    logger.info("🔄 Enhanced monitoring loop started")
    consecutive_errors = 0
    
    while monitoring_active:
        cycle_start = time.time()
        
        try:
            # Refresh Drive service periodically
            refresh_drive_service()
            
            usernames = recorder.load_usernames()
            if not usernames:
                logger.info("📭 No usernames to monitor")
                time.sleep(CHECK_INTERVAL)
                continue
            
            logger.info(f"🔍 Checking {len(usernames)} users...")
            
            # Process users with better error isolation
            for i, username in enumerate(usernames):
                if not monitoring_active:
                    break
                
                try:
                    # Update last check time
                    last_check_times[username] = datetime.now()
                    
                    # Check live status
                    is_live, stream_info = recorder.check_live_status(username)
                    live_status[username] = is_live
                    
                    if is_live:
                        logger.info(f"🔴 {username} is LIVE!")
                        
                        # Check if already recording
                        with active_recordings_lock:
                            already_recording = username in recording_processes
                            if already_recording:
                                # Verify process is still alive
                                process = recording_processes[username]['process']
                                if process.poll() is not None:
                                    logger.warning(f"⚠️ Recording process died for {username}, restarting...")
                                    recorder._cleanup_recording(username)
                                    already_recording = False
                        
                        if not already_recording:
                            logger.info(f"🎬 Starting new recording for {username}")
                            success = recorder.start_recording(username, stream_info)
                            if success:
                                logger.info(f"✅ Recording started for {username}")
                                consecutive_errors = 0  # Reset error count on success
                            else:
                                logger.error(f"❌ Failed to start recording for {username}")
                                consecutive_errors += 1
                        else:
                            # Log active recording status
                            rec_info = recording_processes.get(username)
                            if rec_info:
                                duration = datetime.now() - rec_info['start_time']
                                logger.info(f"📹 Still recording {username} ({duration.total_seconds():.0f}s)")
                    else:
                        # User is not live
                        with active_recordings_lock:
                            if username in recording_processes:
                                logger.info(f"🛑 {username} went offline, stopping recording")
                                recorder.stop_recording(username)
                    
                    # Delay between user checks to prevent rate limiting
                    time.sleep(8)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {username}: {e}")
                    live_status[username] = False
                    consecutive_errors += 1
                    
                    # If too many consecutive errors, try to recover
                    if consecutive_errors > 5:
                        logger.warning("🔄 Too many errors, attempting recovery...")
                        time.sleep(30)
                        
                        # Try to refresh services
                        if drive_service:
                            setup_drive_service()
                        
                        consecutive_errors = 0
            
            # Calculate sleep time to maintain consistent intervals
            cycle_duration = time.time() - cycle_start
            sleep_time = max(CHECK_INTERVAL - cycle_duration, 10)
            
            logger.info(f"⏱️ Cycle completed in {cycle_duration:.1f}s, waiting {sleep_time:.1f}s...")
            
            # Sleep with monitoring check
            for i in range(int(sleep_time)):
                if not monitoring_active:
                    break
                time.sleep(1)
            
            # Garbage collection to prevent memory leaks
            if datetime.now().minute % 10 == 0:  # Every 10 minutes
                gc.collect()
                
        except Exception as e:
            logger.error(f"❌ Critical error in monitoring loop: {e}")
            logger.error(traceback.format_exc())
            consecutive_errors += 1
            
            # Recovery sleep - longer for critical errors
            recovery_sleep = min(60 * consecutive_errors, 300)  # Max 5 minutes
            logger.info(f"🔄 Recovery sleep: {recovery_sleep}s")
            time.sleep(recovery_sleep)
    
    logger.info("🛑 Monitoring loop stopped")

@app.route('/')
def index():
    """Main page - redirect to status"""
    return redirect(url_for('status'))

@app.route('/status')
def status():
    """Enhanced status dashboard"""
    try:
        usernames = recorder.load_usernames()
        
        # Prepare user data with better error handling
        user_data = []
        for username in usernames:
            try:
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
                
            except Exception as e:
                logger.error(f"❌ Error preparing user data for {username}: {e}")
                # Add minimal user info
                user_data.append({
                    'username': username,
                    'is_live': False,
                    'is_recording': False,
                    'error': True
                })
        
        return render_template('status.html',
                             users=user_data,
                             monitoring_active=monitoring_active,
                             drive_connected=drive_service is not None,
                             total_recordings=len(recording_processes),
                             uptime=str(datetime.now() - session_start_time).split('.')[0])
                             
    except Exception as e:
        logger.error(f"❌ Error in status route: {e}")
        return f"Error loading status: {e}", 500

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user to monitoring"""
    try:
        username = request.form.get('username', '').strip()
        
        if username:
            success = recorder.add_username(username)
            if success:
                flash(f"✅ Added @{username} to monitoring", 'success')
            else:
                flash(f"⚠️ @{username} is already being monitored", 'warning')
        else:
            flash("❌ Please enter a valid username", 'error')
    except Exception as e:
        logger.error(f"❌ Error adding user: {e}")
        flash("❌ Error adding user", 'error')
    
    return redirect(url_for('status'))

@app.route('/remove_user', methods=['POST'])
def remove_user():
    """Remove a user from monitoring"""
    try:
        username = request.form.get('username', '').strip()
        
        if username:
            success = recorder.remove_username(username)
            if success:
                flash(f"🗑️ Removed @{username} from monitoring", 'success')
            else:
                flash(f"❌ @{username} not found", 'error')
    except Exception as e:
        logger.error(f"❌ Error removing user: {e}")
        flash("❌ Error removing user", 'error')
    
    return redirect(url_for('status'))

@app.route('/auth/google')
def auth_google():
    """Enhanced Google OAuth flow"""
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
        
        # Build redirect URI properly for Render
        if request.headers.get('X-Forwarded-Proto'):
            scheme = request.headers.get('X-Forwarded-Proto')
        else:
            scheme = request.scheme
        
        host = request.headers.get('Host', request.host)
        redirect_uri = f"{scheme}://{host}/oauth2callback"
        
        # Create OAuth flow
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )
        
        session['state'] = state
        session['redirect_uri'] = redirect_uri
        session['flow_credentials_file'] = credentials_file
        session.permanent = True  # Make session permanent
        
        logger.info(f"🔗 Starting OAuth flow with redirect: {redirect_uri}")
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"❌ OAuth error: {e}")
        flash(f"❌ OAuth setup error: {str(e)}", 'error')
        return redirect(url_for('status'))

@app.route('/oauth2callback')
def oauth2callback():
    """Enhanced OAuth callback with better error handling"""
    try:
        state = session.get('state')
        redirect_uri = session.get('redirect_uri')
        credentials_file = session.get('flow_credentials_file')
        
        if not state or not redirect_uri or not credentials_file:
            flash("❌ OAuth state error - please try again", 'error')
            return redirect(url_for('status'))
        
        # Recreate flow with same parameters
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        
        # Get the authorization response
        authorization_response = request.url
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
            # Ensure HTTPS in the response URL for Render
            authorization_response = authorization_response.replace('http://', 'https://')
        
        # Fetch token
        flow.fetch_token(authorization_response=authorization_response)
        
        credentials = flow.credentials
        
        # Store credentials in session with permanent flag
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        session.permanent = True
        
        # Clean up session
        session.pop('state', None)
        session.pop('redirect_uri', None)
        session.pop('flow_credentials_file', None)
        
        # Setup Drive service
        setup_success = setup_drive_service()
        
        if setup_success:
            # Create Drive folders for all existing users
            usernames = recorder.load_usernames()
            for username in usernames:
                recorder.create_user_folder(username)
            
            flash("✅ Google Drive authorized successfully!", 'success')
            logger.info("✅ Google Drive authorization completed")
            
            # Auto-start monitoring if users exist
            if usernames:
                result = start_monitoring_internal()
                if result['status'] == 'success':
                    flash("🚀 Monitoring started automatically!", 'success')
        else:
            flash("⚠️ Drive authorization completed but service setup failed", 'warning')
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        logger.error(traceback.format_exc())
        flash(f"❌ Authorization failed: {str(e)}", 'error')
    
    return redirect(url_for('status'))

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Start monitoring endpoint"""
    result = start_monitoring_internal()
    return jsonify(result)

def start_monitoring_internal():
    """Enhanced internal function to start monitoring"""
    global monitoring_active, monitoring_thread
    
    try:
        if monitoring_active:
            return {"status": "warning", "message": "Monitoring already active"}
        
        if not drive_service:
            return {"status": "error", "message": "Please authorize Google Drive first"}
        
        usernames = recorder.load_usernames()
        if not usernames:
            return {"status": "error", "message": "No usernames to monitor"}
        
        monitoring_active = True
        monitoring_thread = threading.Thread(
            target=monitoring_loop, 
            daemon=True,
            name="MainMonitoringLoop"
        )
        monitoring_thread.start()
        
        logger.info(f"🚀 Monitoring started for {len(usernames)} users")
        return {"status": "success", "message": f"Monitoring started for {len(usernames)} users"}
        
    except Exception as e:
        logger.error(f"❌ Error starting monitoring: {e}")
        return {"status": "error", "message": f"Failed to start monitoring: {str(e)}"}

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Enhanced stop monitoring"""
    global monitoring_active
    
    try:
        if not monitoring_active:
            return jsonify({"status": "warning", "message": "Monitoring not active"})
        
        monitoring_active = False
        
        # Stop all active recordings gracefully
        with active_recordings_lock:
            active_users = list(recording_processes.keys())
        
        for username in active_users:
            recorder.stop_recording(username)
        
        logger.info("🛑 Monitoring stopped")
        return jsonify({"status": "success", "message": "Monitoring stopped"})
        
    except Exception as e:
        logger.error(f"❌ Error stopping monitoring: {e}")
        return jsonify({"status": "error", "message": f"Failed to stop: {str(e)}"})

@app.route('/test_user/<username>')
def test_user(username):
    """Test endpoint to check a specific user's live status"""
    try:
        is_live, stream_info = recorder.check_live_status(username)
        
        result = {
            'username': username,
            'is_live': is_live,
            'timestamp': datetime.now().isoformat(),
            'stream_info_available': stream_info is not None
        }
        
        if stream_info:
            result['stream_title'] = stream_info.get('title', 'Unknown')
            result['stream_duration'] = stream_info.get('duration', 'Unknown')
        
        logger.info(f"🧪 Test result for {username}: {'LIVE' if is_live else 'OFFLINE'}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Test failed for {username}: {e}")
        return jsonify({
            'username': username,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/status')
def api_status():
    """Enhanced API endpoint for status data"""
    try:
        usernames = recorder.load_usernames()
        
        status_data = {
            'monitoring_active': monitoring_active,
            'drive_connected': drive_service is not None,
            'total_users': len(usernames),
            'live_users': sum(1 for user in usernames if live_status.get(user, False)),
            'recording_users': len(recording_processes),
            'last_update': datetime.now().isoformat(),
            'uptime_seconds': int((datetime.now() - session_start_time).total_seconds()),
            'error_count': error_count,
            'users': []
        }
        
        for username in usernames:
            try:
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
                
            except Exception as e:
                logger.error(f"❌ Error preparing user status for {username}: {e}")
        
        return jsonify(status_data)
        
    except Exception as e:
        logger.error(f"❌ Error in API status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/revoke')
def revoke():
    """Enhanced revoke Google Drive authorization"""
    global drive_service, monitoring_active
    
    try:
        # Stop monitoring first
        monitoring_active = False
        
        # Stop all recordings
        with active_recordings_lock:
            active_users = list(recording_processes.keys())
        
        for username in active_users:
            recorder.stop_recording(username)
        
        # Clear session and service
        with service_lock:
            if 'credentials' in session:
                del session['credentials']
            drive_service = None
        
        flash("🔓 Google Drive authorization revoked", 'info')
        logger.info("🔓 Drive authorization revoked")
        
    except Exception as e:
        logger.error(f"❌ Error revoking authorization: {e}")
        flash("❌ Error revoking authorization", 'error')
    
    return redirect(url_for('status'))

@app.route('/force_check/<username>')
def force_check(username):
    """Force check a specific user (for debugging)"""
    try:
        is_live, stream_info = recorder.check_live_status(username)
        live_status[username] = is_live
        last_check_times[username] = datetime.now()
        
        if is_live:
            flash(f"🔴 {username} is LIVE!", 'success')
        else:
            flash(f"⚪ {username} is offline", 'info')
        
        return redirect(url_for('status'))
        
    except Exception as e:
        logger.error(f"❌ Error force checking {username}: {e}")
        flash(f"❌ Error checking {username}: {str(e)}", 'error')
        return redirect(url_for('status'))

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        health_data = {
            'status': 'healthy',
            'monitoring_active': monitoring_active,
            'drive_connected': drive_service is not None,
            'active_recordings': len(recording_processes),
            'uptime_seconds': int((datetime.now() - session_start_time).total_seconds()),
            'timestamp': datetime.now().isoformat()
        }
        
        # Check if monitoring thread is alive
        if monitoring_active and (not monitoring_thread or not monitoring_thread.is_alive()):
            health_data['status'] = 'degraded'
            health_data['warning'] = 'Monitoring thread not active'
        
        return jsonify(health_data)
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# Enhanced signal handling
def signal_handler(sig, frame):
    """Enhanced shutdown signal handler"""
    global monitoring_active
    
    logger.info("🛑 Shutdown signal received - performing graceful shutdown...")
    monitoring_active = False
    
    # Stop all recordings gracefully
    with active_recordings_lock:
        active_users = list(recording_processes.keys())
    
    for username in active_users:
        logger.info(f"🛑 Stopping recording for {username}...")
        recorder.stop_recording(username)
    
    # Wait for processes to stop
    time.sleep(5)
    
    logger.info("✅ Graceful shutdown completed")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Periodic cleanup function
def periodic_cleanup():
    """Periodic cleanup to prevent resource leaks"""
    while True:
        try:
            time.sleep(600)  # Every 10 minutes
            
            # Clean up dead processes
            with active_recordings_lock:
                dead_users = []
                for username, rec_info in recording_processes.items():
                    if rec_info['process'].poll() is not None:
                        dead_users.append(username)
                
                for username in dead_users:
                    logger.info(f"🧹 Cleaning up dead process for {username}")
                    recorder._cleanup_recording(username)
            
            # Garbage collection
            gc.collect()
            
            # Log memory usage
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"💾 Memory usage: {memory_mb:.1f}MB")
            
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")

if __name__ == '__main__':
    logger.info("🚀 TikTok Livestream Recorder - ENHANCED PRODUCTION VERSION")
    logger.info("=" * 70)
    
    # Create initial folder structures
    usernames = recorder.load_usernames()
    logger.info(f"📋 Loaded {len(usernames)} usernames: {usernames}")
    
    for username in usernames:
        recorder.create_user_folder(username)
    
    # Start periodic cleanup thread
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True, name="PeriodicCleanup")
    cleanup_thread.start()
    
    # Get port from environment (Render sets this)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"🚀 Starting server on port {port}")
    logger.info("📊 Dashboard will be available at the provided URL")
    logger.info("🔗 Authorize Google Drive to enable automatic monitoring")
    
    # Run Flask app with production settings
    try:
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=False, 
            threaded=True,
            use_reloader=False  # Disable reloader in production
        )
    except Exception as e:
        logger.error(f"❌ Server startup error: {e}")
        sys.exit(1)
