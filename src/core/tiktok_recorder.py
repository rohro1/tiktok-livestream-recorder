import subprocess
import requests
import re
import json
import logging
import os
import time
from datetime import datetime
import yt_dlp

logger = logging.getLogger(__name__)

class TikTokRecorder:
    def __init__(self, status_tracker=None):
        self.recording_process = None
        self.is_recording = False
        self.status_tracker = status_tracker
        self.current_username = None
        
    def check_if_live(self, username):
        """Check if a TikTok user is currently live and return stream URL"""
        try:
            # Try multiple methods to check if user is live
            
            # Method 1: Use yt-dlp to check for live stream
            live_url = self._check_live_with_ytdlp(username)
            if live_url:
                logger.info(f"{username} is live (detected via yt-dlp)")
                return live_url
            
            # Method 2: Direct API check (backup method)
            live_url = self._check_live_direct_api(username)
            if live_url:
                logger.info(f"{username} is live (detected via direct API)")
                return live_url
            
            # Method 3: Web scraping fallback
            live_url = self._check_live_web_scraping(username)
            if live_url:
                logger.info(f"{username} is live (detected via web scraping)")
                return live_url
            
            logger.debug(f"{username} is not live")
            return None
            
        except Exception as e:
            logger.error(f"Error checking if {username} is live: {e}")
            return None
    
    def _check_live_with_ytdlp(self, username):
        """Use yt-dlp to check for live stream"""
        try:
            profile_url = f"https://www.tiktok.com/@{username}/live"
            
            # Configure yt-dlp options
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'format': 'best[height<=480]',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(profile_url, download=False)
                    if info and info.get('is_live'):
                        return info.get('url') or profile_url
                except yt_dlp.DownloadError:
                    # User might not be live or profile doesn't exist
                    pass
            
            return None
            
        except Exception as e:
            logger.debug(f"yt-dlp check failed for {username}: {e}")
            return None
    
    def _check_live_direct_api(self, username):
        """Direct API check for live status"""
        try:
            # TikTok live API endpoint (may change)
            api_url = f"https://www.tiktok.com/api/live/detail/?aid=1988&unique_id={username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.tiktok.com/',
                'Accept': 'application/json, text/plain, */*',
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                live_room = data.get('LiveRoomInfo', {}).get('liveRoom')
                
                if live_room and live_room.get('status') == 2:  # Status 2 = live
                    stream_data = live_room.get('streamData', {})
                    pull_data = stream_data.get('pullData', {})
                    
                    # Try to get stream URL
                    stream_url = None
                    if pull_data.get('streamData'):
                        stream_url = pull_data['streamData']
                    elif pull_data.get('options', {}).get('qualities', []):
                        qualities = pull_data['options']['qualities']
                        # Get 480p or best available quality
                        for quality in qualities:
                            if '480' in quality.get('name', ''):
                                stream_url = quality.get('sdkKey')
                                break
                        if not stream_url and qualities:
                            stream_url = qualities[0].get('sdkKey')
                    
                    if stream_url:
                        return stream_url
                    else:
                        # Return profile live URL if we can't get direct stream
                        return f"https://www.tiktok.com/@{username}/live"
            
            return None
            
        except Exception as e:
            logger.debug(f"Direct API check failed for {username}: {e}")
            return None
    
    def _check_live_web_scraping(self, username):
        """Web scraping fallback method"""
        try:
            profile_url = f"https://www.tiktok.com/@{username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(profile_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                
                # Look for live indicators in the HTML
                live_indicators = [
                    'isLive":true',
                    '"status":2',
                    'LIVE</span>',
                    'live-dot',
                    'live-status'
                ]
                
                for indicator in live_indicators:
                    if indicator in content:
                        logger.info(f"Found live indicator '{indicator}' for {username}")
                        return f"https://www.tiktok.com/@{username}/live"
            
            return None
            
        except Exception as e:
            logger.debug(f"Web scraping check failed for {username}: {e}")
            return None
    
    def start_recording(self, stream_url, output_file):
        """Start recording a live stream"""
        try:
            if self.is_recording:
                logger.warning("Already recording, stopping previous recording")
                self.stop_recording()
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Use yt-dlp for recording
            ydl_opts = {
                'format': 'best[height<=480]/best',
                'outtmpl': output_file,
                'live_from_start': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            }
            
            logger.info(f"Starting recording: {stream_url} -> {output_file}")
            
            # Start recording in a separate process
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([stream_url])
            
            self.is_recording = True
            logger.info(f"Recording started successfully: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            return False
    
    def stop_recording(self):
        """Stop the current recording"""
        try:
            if self.recording_process:
                self.recording_process.terminate()
                self.recording_process.wait(timeout=10)
                self.recording_process = None
            
            self.is_recording = False
            logger.info("Recording stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            self.is_recording = False
            return False
    
    def get_user_info(self, username):
        """Get basic user information"""
        try:
            profile_url = f"https://www.tiktok.com/@{username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(profile_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Extract basic info from HTML if possible
                content = response.text
                
                # Try to find display name
                display_name_match = re.search(r'"nickname":"([^"]+)"', content)
                display_name = display_name_match.group(1) if display_name_match else username
                
                # Try to find follower count
                follower_match = re.search(r'"followerCount":(\d+)', content)
                followers = int(follower_match.group(1)) if follower_match else 0
                
                return {
                    'username': username,
                    'display_name': display_name,
                    'followers': followers,
                    'profile_url': profile_url
                }
            
            return {
                'username': username,
                'display_name': username,
                'followers': 0,
                'profile_url': profile_url
            }
            
        except Exception as e:
            logger.error(f"Error getting user info for {username}: {e}")
            return {
                'username': username,
                'display_name': username,
                'followers': 0,
                'profile_url': f"https://www.tiktok.com/@{username}"
            }
    
    def is_user_live(self, username):
        """Check if user is live using check_if_live method"""
        try:
            stream_url = self.check_if_live(username)
            is_live = bool(stream_url)
            if self.status_tracker:
                self.status_tracker.update_user_status(username, is_live=is_live)
            return is_live
        except Exception as e:
            logger.error(f"Error checking if {username} is live: {e}")
            return False

    def record_stream(self, username):
        """Record a user's livestream"""
        try:
            stream_url = self.check_if_live(username)
            if not stream_url:
                logger.error(f"User {username} is not live")
                return None

            output_dir = os.path.join('recordings', username)
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(output_dir, f'{username}_{timestamp}.mp4')

            return self.start_recording(stream_url, output_file)

        except Exception as e:
            logger.error(f"Error recording {username}: {e}")
            return None