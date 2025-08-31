"""
TikTok Stream Recorder
Handles livestream detection and recording using yt-dlp and ffmpeg
"""

import os
import subprocess
import time
import logging
from datetime import datetime
import yt_dlp
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class TikTokRecorder:
    def __init__(self, status_tracker=None):
        self.status_tracker = status_tracker
        self.recordings_dir = "recordings"
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # yt-dlp configuration
        self.ydl_opts = {
            'format': 'best[height<=480]',  # 480p max quality
            'noplaylist': True,
            'no_warnings': True,
            'quiet': True,
            'extractaudio': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
        }

    def get_tiktok_live_url(self, username):
        """
        Get TikTok live stream URL - only returns URL if user is actually live
        Returns None if user is not live
        """
        try:
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            # Use yt-dlp to extract stream info - this is the most reliable method
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(live_url, download=False)
                    if info and info.get('is_live', False) and 'url' in info:
                        logger.info(f"Found live stream for {username}")
                        return info['url']
                except yt_dlp.DownloadError as e:
                    if "not currently live" in str(e).lower():
                        logger.debug(f"User {username} is not live")
                        return None
                    else:
                        logger.debug(f"yt-dlp error for {username}: {e}")
                except Exception as e:
                    logger.debug(f"yt-dlp extraction failed for {username}: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting live URL for {username}: {e}")
            return None

    def _check_live_status_alternative(self, username):
        """Alternative method to check if user is live"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Try to get the live stream URL directly with yt-dlp
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                try:
                    # Try to extract info - this will fail if not live
                    info = ydl.extract_info(live_url, download=False)
                    if info and info.get('is_live', False):
                        logger.info(f"User {username} confirmed live via yt-dlp")
                        return live_url
                except yt_dlp.DownloadError as e:
                    if "not currently live" in str(e).lower():
                        logger.debug(f"User {username} is not live")
                        return None
                except Exception:
                    pass
            
            # If yt-dlp fails, try web scraping as backup
            try:
                profile_url = f"https://www.tiktok.com/@{username}"
                response = requests.get(profile_url, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    # Look for specific live indicators - be more strict
                    content = response.text.lower()
                    if ('"is_live":true' in content or 
                        'live_status":1' in content or
                        'room_id' in content and 'live' in content):
                        logger.info(f"User {username} appears live via web check")
                        return live_url
            except Exception as e:
                logger.debug(f"Web check failed for {username}: {e}")
            
            return None
            
        except Exception as e:
            logger.debug(f"Alternative live check failed for {username}: {e}")
            return None

    def is_user_live(self, username):
        """
        Check if a user is currently live
        Returns True if live, False otherwise
        """
        try:
            # Use yt-dlp as primary method - it's most reliable
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                try:
                    info = ydl.extract_info(live_url, download=False)
                    if info and info.get('is_live', False):
                        logger.debug(f"User {username} is live")
                        return True
                except yt_dlp.DownloadError as e:
                    if "not currently live" in str(e).lower():
                        logger.debug(f"User {username} is not live")
                        return False
                except Exception as e:
                    logger.debug(f"yt-dlp check failed for {username}: {e}")
            
            # Don't use alternative method as it's unreliable
            return False
            
        except Exception as e:
            logger.error(f"Error checking live status for {username}: {e}")
            return False

    def record_stream(self, username):
        """
        Record a user's livestream
        Returns the output file path if successful, None otherwise
        """
        try:
            # Get live stream URL - this also verifies user is live
            stream_url = self.get_tiktok_live_url(username)
            if not stream_url:
                logger.warning(f"No live stream found for {username}")
                return None

            # Generate output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(
                self.recordings_dir, 
                f"{username}_{timestamp}.mp4"
            )

            logger.info(f"Starting recording for {username}: {output_file}")
            
            # Update status
            if self.status_tracker:
                self.status_tracker.update_user_status(
                    username,
                    is_live=True,
                    recording_start=datetime.now(),
                    recording_file=output_file
                )

            # Try recording with yt-dlp first
            success = self._record_with_ytdlp(username, output_file)
            
            if success and os.path.exists(output_file):
                logger.info(f"Recording completed: {output_file}")
                return output_file
            else:
                logger.error(f"Recording failed for {username}")
                # Clean up failed file
                if os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                    except Exception:
                        pass
                return None

        except Exception as e:
            logger.error(f"Error recording stream for {username}: {e}")
            return None

    def _record_with_ytdlp(self, username, output_file):
        """Record using yt-dlp directly with username"""
        try:
            live_url = f"https://www.tiktok.com/@{username}/live"
            
            ydl_opts = {
                'format': 'best[height<=480]/best',  # Prefer 480p
                'outtmpl': output_file,
                'live_from_start': True,
                'wait_for_video': (1, 60),  # Wait up to 60 seconds for stream
                'no_warnings': True,
                'quiet': False,  # Enable some output for debugging
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Starting yt-dlp recording for {username}")
                ydl.download([live_url])
            
            # Check if file was created and has content
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                if file_size > 100000:  # At least 100KB
                    logger.info(f"yt-dlp recording successful for {username}: {file_size} bytes")
                    return True
                else:
                    logger.warning(f"yt-dlp created small file for {username}: {file_size} bytes")
                    return False
            else:
                logger.error(f"yt-dlp did not create output file for {username}")
                return False
            
        except yt_dlp.DownloadError as e:
            if "not currently live" in str(e).lower():
                logger.info(f"User {username} is not live (yt-dlp confirmed)")
            else:
                logger.error(f"yt-dlp download error for {username}: {e}")
            return False
        except Exception as e:
            logger.error(f"yt-dlp recording failed for {username}: {e}")
            return False

    def _record_with_ffmpeg(self, stream_url, output_file, username):
        """Fallback recording using ffmpeg directly"""
        try:
            # FFmpeg command for recording
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c', 'copy',
                '-f', 'mp4',
                '-t', '3600',  # Max 1 hour recording
                output_file,
                '-y'  # Overwrite output file
            ]
            
            logger.info(f"Starting ffmpeg recording for {username}")
            
            # Run ffmpeg
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor the process
            while True:
                if process.poll() is not None:
                    break
                    
                # Check if user is still live every 30 seconds
                time.sleep(30)
                if not self.is_user_live(username):
                    logger.info(f"User {username} went offline, stopping recording")
                    process.terminate()
                    break
            
            # Wait for process to finish
            stdout, stderr = process.communicate(timeout=60)
            
            if process.returncode == 0:
                logger.info(f"FFmpeg recording completed for {username}")
                return True
            else:
                logger.error(f"FFmpeg failed for {username}: {stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.warning(f"FFmpeg timeout for {username}")
            process.kill()
            return False
        except Exception as e:
            logger.error(f"FFmpeg error for {username}: {e}")
            return False

    def get_recording_duration(self, file_path):
        """Get duration of a recording file"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                return 0
                
        except Exception as e:
            logger.error(f"Error getting duration for {file_path}: {e}")
            return 0

    def cleanup_old_recordings(self, days=7):
        """Clean up recordings older than specified days"""
        try:
            cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
            removed_count = 0
            
            for file_name in os.listdir(self.recordings_dir):
                file_path = os.path.join(self.recordings_dir, file_name)
                
                if os.path.isfile(file_path):
                    file_time = os.path.getmtime(file_path)
                    
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        removed_count += 1
                        logger.info(f"Removed old recording: {file_name}")
            
            logger.info(f"Cleaned up {removed_count} old recordings")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up recordings: {e}")
            return 0