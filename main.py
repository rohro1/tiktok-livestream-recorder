#!/usr/bin/env python3
"""
TikTok Livestream Recorder - FIXED Production Version
Automatically monitors TikTok users and records their livestreams with reliable detection
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

# Flask app configuration
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
RECORDINGS_DIR = "recordings"
USERNAMES_FILE = "usernames.txt"
CHECK_INTERVAL = 30  # seconds between checks
RECORDING_QUALITY = "best[height<=480]/worst[height<=480]/best"  # 480p max quality for space saving

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

class TikTokLiveDetector:
    """Enhanced TikTok live detection using multiple reliable methods"""
    
    def __init__(self):
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Android 11; Mobile; rv:68.0) Gecko/68.0 Firefox/88.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet'
        ]
    
    def get_headers(self, mobile=True):
        """Get randomized headers for requests"""
        if mobile:
            return {
                'User-Agent': random.choice(self.user_agents[:2]),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none'
            }
        else:
            return {
                'User-Agent': random.choice(self.user_agents[2:]),
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.tiktok.com/'
            }
    
    def check_live_with_ytdlp(self, username):
        """Use yt-dlp to check if user is live (most reliable method)"""
        try:
            clean_username = username.replace('@', '').strip()
            live_url = f"https://www.tiktok.com/@{clean_username}/live"
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'timeout': 15,
                'socket_timeout': 10,
                'http_headers': self.get_headers(mobile=True)
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(live_url, download=False)
                    if info and (info.get('url') or info.get('formats')):
                        logger.info(f"✅ yt-dlp: {username} is LIVE!")
                        return True, info
                except yt_dlp.utils.DownloadError as e:
                    if "not currently live" in str(e).lower() or "private" in str(e).lower():
                        return False, None
                    elif "geo" in str(e).lower() or "region" in str(e).lower():
                        logger.warning(f"⚠️ Geo-blocked for {username}, trying alternative methods")
                        return False, None
                    else:
                        raise e
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ yt-dlp check failed for {username}: {e}")
            return False, None
    
    def check_live_webpage_method(self, username):
        """Check live status by parsing TikTok webpage"""
        try:
            clean_username = username.replace('@', '').strip()
            
            # Try different URL patterns
            urls_to_try = [
                f"https://www.tiktok.com/@{clean_username}/live",
                f"https://m.tiktok.com/@{clean_username}/live",
                f"https://www.tiktok.com/@{clean_username}"
            ]
            
            for url in urls_to_try:
                try:
                    response = self.session.get(
                        url, 
                        headers=self.get_headers(mobile='m.tiktok' in url),
                        timeout=10,
                        allow_redirects=True
                    )
                    
                    if response.status_code == 200:
                        content = response.text.lower()
                        
                        # Look for live indicators in page content
                        live_indicators = [
                            '"islive":true',
                            '"roomid":"',
                            'class="live-indicator"',
                            'data-live="true"',
                            '"status":2',  # TikTok live status code
                            'webcast/room/',
                            'live_room',
                            '"room_id":"'
                        ]
                        
                        offline_indicators = [
                            '"islive":false',
                            'not currently live',
                            'no live streams',
                            'user is not live',
                            '"status":0'
                        ]
                        
                        # Check for live indicators
                        live_found = any(indicator in content for indicator in live_indicators)
                        offline_found = any(indicator in content for indicator in offline_indicators)
                        
                        if live_found and not offline_found:
                            logger.info(f"✅ Webpage: {username} appears to be LIVE!")
                            return True
                        elif offline_found:
                            return False
                        
                        # Look for room_id in JSON data
                        room_id_match = re.search(r'"room_id["\s]*:["\s]*([^",\s]+)', content)
                        if room_id_match:
                            room_id = room_id_match.group(1).strip('"')
                            if room_id and room_id != '0' and room_id != '':
                                logger.info(f"✅ Found room_id: {username} is LIVE! (Room: {room_id})")
                                return True
                
                except requests.RequestException:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Webpage check failed for {username}: {e}")
            return False
    
    def check_live_status(self, username):
        """Main live detection method combining multiple approaches"""
        try:
            clean_username = username.replace('@', '').strip()
            
            # Method 1: Try yt-dlp first (most reliable)
            logger.debug(f"🔍 Checking {username} with yt-dlp...")
            is_live_ytdlp, stream_info = self.check_live_with_ytdlp(username)
            
            if is_live_ytdlp:
                return True, stream_info
            
            # Method 2: Try webpage parsing
            logger.debug(f"🔍 Checking {username} with webpage method...")
            is_live_webpage = self.check_live_webpage_method(username)
            
            if is_live_webpage:
                # If webpage says live, try to get stream info with yt-dlp again
                time.sleep(2)  # Brief delay
                is_live_ytdlp_retry, stream_info = self.check_live_with_ytdlp(username)
                return True, stream_info
            
            logger.info(f"❌ All checks: {username} is not live")
            return False, None
            
        except Exception as e:
            logger.error(f"❌ Live detection error for {username}: {e}")
            return False, None

class StreamRecorder:
    def __init__(self):
        self.live_detector = TikTokLiveDetector()
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
    
    def start_recording(self, username, stream_info=None):
        """Start recording with FFmpeg - FIXED VERSION"""
        if username in recording_processes:
            logger.info(f"📹 Already recording {username}")
            return False
        
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
            stream_url = None
            if stream_info.get('url'):
                stream_url = stream_info['url']
            elif stream_info.get('formats'):
                # Find best format under 480p
                best_format = None
                for fmt in stream_info['formats']:
                    if fmt.get('url') and fmt.get('height', 0) <= 480:
                        if not best_format or (fmt.get('height', 0) > best_format.get('height', 0)):
                            best_format = fmt
                
                if best_format:
                    stream_url = best_format['url']
                elif stream_info['formats']:
                    # Fallback to first available URL
                    stream_url = stream_info['formats'][0].get('url')
            
            if not stream_url:
                logger.error(f"❌ No stream URL found for {username}")
                return False
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{username}_{timestamp}.mp4"
            user_dir = os.path.join(RECORDINGS_DIR, username)
            filepath = os.path.join(user_dir, filename)
            
            logger.info(f"🎬 Starting recording for {username}")
            logger.info(f"📁 Output: {filepath}")
            logger.info(f"🔗 Stream URL: {stream_url[:100]}...")
            
            # Enhanced FFmpeg command for reliable 480p recording
            cmd = [
                'ffmpeg',
                '-headers', 'User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15',
                '-i', stream_url,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'faster',        # Balanced speed/quality
                '-crf', '28',              # Good quality for 480p
                '-maxrate', '1200k',       # Max bitrate for 480p
                '-bufsize', '2400k',       # Buffer size
                '-vf', 'scale=-2:480',     # Force 480p, maintain aspect ratio
                '-movflags', '+faststart', # Better for streaming
                '-reconnect', '1',         # Auto-reconnect
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '10',
                '-rw_timeout', '10000000', # 10 second read timeout
                '-y',                      # Overwrite output file
                filepath
            ]
            
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
                'stream_info': stream_info
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
            # Clean up if failed
            if username in recording_processes:
                del recording_processes[username]
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
            
            last_size = 0
            no_growth_count = 0
            
            while process.poll() is None:
                # Check if file exists and is growing
                if os.path.exists(filepath):
                    current_size = os.path.getsize(filepath)
                    duration = datetime.now() - start_time
                    
                    # Check if file is growing
                    if current_size > last_size:
                        no_growth_count = 0
                        logger.info(f"📊 {username}: {duration.total_seconds():.0f}s, {current_size/1024/1024:.1f}MB")
                    else:
                        no_growth_count += 1
                        if no_growth_count > 6:  # 60 seconds without growth
                            logger.warning(f"⚠️ Recording stalled for {username}, stopping...")
                            process.terminate()
                            break
                    
                    last_size = current_size
                else:
                    logger.warning(f"⚠️ Recording file not found: {filepath}")
                
                time.sleep(10)  # Check every 10 seconds
            
            # Process ended
            return_code = process.returncode
            duration = datetime.now() - start_time
            
            if return_code == 0:
                logger.info(f"✅ Recording completed for {username} ({duration.total_seconds():.0f}s)")
            else:
                logger.warning(f"⚠️ Recording ended with code {return_code} for {username}")
            
            # Check final file and upload
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                if file_size > 50000:  # At least 50KB
                    logger.info(f"💾 Recording saved: {filepath} ({file_size/1024/1024:.1f}MB)")
                    
                    # Upload to Google Drive if authorized
                    if drive_service:
                        threading.Thread(
                            target=self.upload_to_drive,
                            args=(filepath, username),
                            daemon=True
                        ).start()
                else:
                    logger.warning(f"⚠️ Recording file too small: {filepath} ({file_size} bytes)")
                    try:
                        os.remove(filepath)
                        logger.info(f"🗑️ Removed small file: {filepath}")
                    except:
                        pass
            
            # Clean up
            if username in recording_processes:
                del recording_processes[username]
                logger.info(f"🧹 Cleaned up recording process for {username}")
                
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
            
            logger.info(f"☁️ Starting Drive upload for {username}...")
            
            # Create folder structure: TikTok_Recordings/Username/YYYY-MM/
            current_date = datetime.now()
            year_month = current_date.strftime('%Y-%m')
            
            # Get or create main folder
            main_folder_id = self.get_or_create_folder(drive_service, "TikTok_Recordings")
            if not main_folder_id:
                logger.error(f"❌ Cannot create main Drive folder")
                return False
            
            # Get or create user folder
            user_folder_id = self.get_or_create_folder(drive_service, username, main_folder_id)
            if not user_folder_id:
                logger.error(f"❌ Cannot create user Drive folder")
                return False
            
            # Get or create date folder
            date_folder_id = self.get_or_create_folder(drive_service, year_month, user_folder_id)
            if not date_folder_id:
                logger.error(f"❌ Cannot create date Drive folder")
                return False
            
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
            
            logger.info(f"✅ Uploaded to Drive: {filename} (ID: {file_id})")
            
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
    """Setup Google Drive service with proper error handling"""
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
    """Enhanced monitoring loop with better error handling"""
    global monitoring_active
    
    logger.info("🔄 Monitoring loop started")
    
    while monitoring_active:
        try:
            usernames = recorder.load_usernames()
            if not usernames:
                logger.info("📭 No usernames to monitor")
                time.sleep(CHECK_INTERVAL)
                continue
                
            logger.info(f"🔍 Checking {len(usernames)} users...")
            
            for username in usernames:
                if not monitoring_active:
                    break
                
                try:
                    # Update last check time
                    last_check_times[username] = datetime.now()
                    
                    # Check live status using enhanced detection
                    is_live, stream_info = recorder.check_live_status(username)
                    live_status[username] = is_live
                    
                    if is_live:
                        logger.info(f"🔴 {username} is LIVE!")
                        
                        # Start recording if not already recording
                        if username not in recording_processes:
                            logger.info(f"🎬 Starting recording for {username}")
                            success = recorder.start_recording(username, stream_info)
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
                                recorder.start_recording(username, stream_info)
                            else:
                                duration = datetime.now() - recording_processes[username]['start_time']
                                logger.info(f"📹 Still recording {username} ({duration.total_seconds():.0f}s)")
                    else:
                        # User is not live
                        if username in recording_processes:
                            logger.info(f"🛑 {username} went offline, stopping recording")
                            recorder.stop_recording(username)
                    
                    # Delay between user checks to avoid rate limiting
                    time.sleep(5)
                    
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
    """Status dashboard with enhanced user information"""
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
    """Start Google OAuth flow - FIXED VERSION"""
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
        
        # Build redirect URI properly
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
        
        logger.info(f"🔗 Starting OAuth flow with redirect: {redirect_uri}")
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"❌ OAuth error: {e}")
        flash(f"❌ OAuth setup error: {str(e)}", 'error')
        return redirect(url_for('status'))

@app.route('/oauth2callback')
def oauth2callback():
    """Handle OAuth callback - FIXED VERSION"""
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
        
        # Store credentials in session
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
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
            
            # Auto-start monitoring
            if usernames:
                start_monitoring_internal()
                flash("🚀 Monitoring started automatically!", 'success')
        else:
            flash("⚠️ Drive authorization completed but service setup failed", 'warning')
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        flash(f"❌ Authorization failed: {str(e)}", 'error')
    
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
    return {"status": "success", "message": f"Monitoring started for {len(usernames)} users"}

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
    """API endpoint for status data"""
    usernames = recorder.load_usernames()
    
    status_data = {
        'monitoring_active': monitoring_active,
        'drive_connected': drive_service is not None,
        'total_users': len(usernames),
        'live_users': sum(1 for user in usernames if live_status.get(user, False)),
        'recording_users': len(recording_processes),
        'last_update': datetime.now().isoformat(),
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

@app.route('/revoke')
def revoke():
    """Revoke Google Drive authorization"""
    global drive_service
    
    # Stop monitoring first
    global monitoring_active
    monitoring_active = False
    
    # Stop all recordings
    for username in list(recording_processes.keys()):
        recorder.stop_recording(username)
    
    # Clear session and service
    if 'credentials' in session:
        del session['credentials']
    
    drive_service = None
    flash("🔓 Google Drive authorization revoked", 'info')
    
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
        flash(f"❌ Error checking {username}: {str(e)}", 'error')
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
    logger.info("🚀 TikTok Livestream Recorder - ENHANCED VERSION")
    logger.info("=" * 60)
    
    # Create initial folder structures
    usernames = recorder.load_usernames()
    logger.info(f"📋 Loaded {len(usernames)} usernames")
    
    for username in usernames:
        recorder.create_user_folder(username)
    
    # Setup Drive service if credentials exist in session (for development)
    if 'credentials' in session:
        setup_drive_service()
    
    # Get port from environment (Render sets this)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"🚀 Starting server on port {port}")
    logger.info("📊 Dashboard will be available at the provided URL")
    logger.info("🔗 Make sure to authorize Google Drive for cloud uploads")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
