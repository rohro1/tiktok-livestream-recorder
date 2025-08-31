#!/usr/bin/env python3
"""
Background Recording Worker
Standalone worker for recording TikTok livestreams
Can be run independently or as part of the main application
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from core.tiktok_recorder import TikTokRecorder
from utils.status_tracker import StatusTracker
from utils.google_drive_uploader import GoogleDriveUploader
from utils.oauth_drive import DriveOAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/recorder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RecorderWorker:
    def __init__(self):
        self.status_tracker = StatusTracker()
        self.recorder = TikTokRecorder(self.status_tracker)
        self.oauth_helper = DriveOAuth()
        self.drive_uploader = None
        self.active_recordings = {}
        self.monitoring_active = False
        
        # Create required directories
        os.makedirs('recordings', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Initialize Google Drive if credentials exist
        self._init_drive()

    def _init_drive(self):
        """Initialize Google Drive uploader if credentials available"""
        try:
            creds = self.oauth_helper.load_credentials()
            if creds and creds.valid:
                self.drive_uploader = GoogleDriveUploader(creds)
                logger.info("Google Drive uploader initialized")
            else:
                logger.warning("No valid Google Drive credentials found")
        except Exception as e:
            logger.error(f"Error initializing Google Drive: {e}")

    def load_usernames(self):
        """Load usernames from file"""
        try:
            with open('usernames.txt', 'r') as f:
                usernames = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(usernames)} usernames")
            return usernames
        except FileNotFoundError:
            logger.warning("usernames.txt not found")
            return []

    def record_user_stream(self, username):
        """Record a user's livestream in a separate thread"""
        try:
            logger.info(f"Starting recording thread for {username}")
            
            # Record the stream
            output_file = self.recorder.record_stream(username)
            
            if output_file and os.path.exists(output_file):
                logger.info(f"Recording completed for {username}: {output_file}")
                
                # Upload to Google Drive
                if self.drive_uploader:
                    try:
                        drive_url = self.drive_uploader.upload_video(output_file, username)
                        if drive_url:
                            self.status_tracker.update_user_status(
                                username,
                                drive_link=drive_url
                            )
                            logger.info(f"Uploaded to Drive: {drive_url}")
                            
                            # Clean up local file after successful upload
                            try:
                                os.remove(output_file)
                                logger.info(f"Cleaned up local file: {output_file}")
                            except Exception as e:
                                logger.warning(f"Could not remove local file: {e}")
                        else:
                            logger.error(f"Drive upload failed for {username}")
                    except Exception as e:
                        logger.error(f"Drive upload error: {e}")
                else:
                    logger.info(f"No Drive uploader configured, keeping local file: {output_file}")
            else:
                logger.error(f"Recording failed for {username}")
                
        except Exception as e:
            logger.error(f"Error in recording thread for {username}: {e}")
        finally:
            # Remove from active recordings
            if username in self.active_recordings:
                del self.active_recordings[username]

    def monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Starting monitoring loop")
        self.monitoring_active = True
        
        while self.monitoring_active:
            try:
                usernames = self.load_usernames()
                
                if not usernames:
                    logger.warning("No usernames to monitor")
                    time.sleep(60)
                    continue
                
                for username in usernames:
                    if not self.monitoring_active:
                        break
                    
                    try:
                        # Check if user is live
                        is_live = self.recorder.is_user_live(username)
                        
                        # Update status
                        self.status_tracker.update_user_status(
                            username,
                            is_live=is_live,
                            last_check=datetime.now()
                        )
                        
                        if is_live and username not in self.active_recordings:
                            # Start recording
                            logger.info(f"User {username} went live, starting recording")
                            thread = threading.Thread(
                                target=self.record_user_stream,
                                args=(username,),
                                daemon=True
                            )
                            thread.start()
                            self.active_recordings[username] = thread
                            
                        elif not is_live and username in self.active_recordings:
                            logger.info(f"User {username} went offline")
                            
                    except Exception as e:
                        logger.error(f"Error checking {username}: {e}")
                    
                    # Small delay between users
                    time.sleep(2)
                
                # Wait before next monitoring cycle
                logger.debug(f"Monitoring cycle complete. Active recordings: {len(self.active_recordings)}")
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)
        
        logger.info("Monitoring loop stopped")

    def start_monitoring(self):
        """Start monitoring in background thread"""
        if not self.monitoring_active:
            thread = threading.Thread(target=self.monitoring_loop, daemon=True)
            thread.start()
            logger.info("Background monitoring started")

    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring_active = False
        logger.info("Monitoring stop requested")

    def cleanup_old_data(self):
        """Clean up old recordings and status data"""
        try:
            # Clean up old recordings (7 days)
            removed_recordings = self.recorder.cleanup_old_recordings(days=7)
            
            # Clean up old status data (30 days)
            removed_status = self.status_tracker.cleanup_old_data(days=30)
            
            logger.info(f"Cleanup complete: {removed_recordings} recordings, {removed_status} status entries")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_status(self):
        """Get current worker status"""
        return {
            'monitoring_active': self.monitoring_active,
            'active_recordings': list(self.active_recordings.keys()),
            'drive_connected': self.drive_uploader is not None,
            'total_users': len(self.load_usernames())
        }

def main():
    """Main function for standalone execution"""
    logger.info("Starting TikTok Livestream Recorder Worker")
    
    worker = RecorderWorker()
    
    try:
        # Start monitoring
        worker.start_monitoring()
        
        # Keep main thread alive
        while True:
            time.sleep(300)  # Check every 5 minutes
            
            # Periodic cleanup
            worker.cleanup_old_data()
            
            # Log status
            status = worker.get_status()
            logger.info(f"Status: {status}")
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        worker.stop_monitoring()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        logger.info("Worker shutting down")

if __name__ == '__main__':
    main()