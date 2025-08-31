"""
Status Tracker
Thread-safe tracking of user livestream statuses
"""

import json
import threading
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class StatusTracker:
    def __init__(self, status_file='status.json'):
        self.status_file = status_file
        self.lock = threading.Lock()
        self.data = self._load_status()

    def _load_status(self):
        """Load status data from file"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r') as f:
                    data = json.load(f)
                logger.info(f"Loaded status data for {len(data)} users")
                return data
            else:
                logger.info("No existing status file, starting fresh")
                return {}
        except Exception as e:
            logger.error(f"Error loading status file: {e}")
            return {}

    def _save_status(self):
        """Save status data to file"""
        try:
            with open(self.status_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving status file: {e}")

    def update_user_status(self, username, **kwargs):
        """
        Update user status with thread safety
        
        Args:
            username (str): TikTok username
            **kwargs: Status fields to update
                - is_live (bool): Current live status
                - last_check (datetime): Last time we checked
                - recording_start (datetime): When recording started
                - recording_end (datetime): When recording ended
                - recording_file (str): Current/last recording file
                - last_recording (str): Path to last completed recording
                - drive_link (str): Google Drive link to recording
        """
        with self.lock:
            if username not in self.data:
                self.data[username] = {
                    'username': username,
                    'is_live': False,
                    'last_check': None,
                    'last_online': None,
                    'recording_start': None,
                    'recording_end': None,
                    'recording_file': None,
                    'last_recording': None,
                    'drive_link': None,
                    'total_recordings': 0,
                    'last_duration': 0
                }

            user_data = self.data[username]
            
            # Update provided fields
            for key, value in kwargs.items():
                if key in user_data:
                    user_data[key] = value

            # Special logic for certain updates
            if 'is_live' in kwargs:
                if kwargs['is_live']:
                    user_data['last_online'] = datetime.now()
                
            if 'recording_end' in kwargs:
                user_data['total_recordings'] += 1
                
                # Calculate duration if we have start and end times
                if user_data['recording_start'] and kwargs['recording_end']:
                    try:
                        start_time = datetime.fromisoformat(str(user_data['recording_start']).replace('Z', '+00:00'))
                        end_time = datetime.fromisoformat(str(kwargs['recording_end']).replace('Z', '+00:00'))
                        duration = (end_time - start_time).total_seconds()
                        user_data['last_duration'] = duration
                    except Exception as e:
                        logger.debug(f"Could not calculate duration for {username}: {e}")

            # Save to file
            self._save_status()
            
            logger.debug(f"Updated status for {username}: {kwargs}")

    def get_user_status(self, username):
        """Get status for a specific user"""
        with self.lock:
            if username in self.data:
                return self.data[username].copy()
            else:
                return {
                    'username': username,
                    'is_live': False,
                    'last_check': None,
                    'last_online': None,
                    'recording_start': None,
                    'recording_end': None,
                    'recording_file': None,
                    'last_recording': None,
                    'drive_link': None,
                    'total_recordings': 0,
                    'last_duration': 0
                }

    def get_all_statuses(self):
        """Get status for all users"""
        with self.lock:
            return self.data.copy()

    def get_live_users(self):
        """Get list of currently live users"""
        with self.lock:
            live_users = []
            for username, data in self.data.items():
                if data.get('is_live', False):
                    live_users.append(username)
            return live_users

    def get_recording_users(self):
        """Get list of users currently being recorded"""
        with self.lock:
            recording_users = []
            for username, data in self.data.items():
                if (data.get('recording_start') and 
                    not data.get('recording_end')):
                    recording_users.append(username)
            return recording_users

    def cleanup_old_data(self, days=30):
        """Remove old status data for users not seen in X days"""
        with self.lock:
            cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
            users_to_remove = []
            
            for username, data in self.data.items():
                last_check = data.get('last_check')
                if last_check:
                    try:
                        if isinstance(last_check, str):
                            check_time = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                        else:
                            check_time = last_check
                        
                        if check_time.timestamp() < cutoff_time:
                            users_to_remove.append(username)
                    except Exception:
                        # If we can't parse the time, remove it
                        users_to_remove.append(username)

            # Remove old users
            for username in users_to_remove:
                del self.data[username]
                logger.info(f"Removed old status data for {username}")

            if users_to_remove:
                self._save_status()
                logger.info(f"Cleaned up status data for {len(users_to_remove)} users")

            return len(users_to_remove)

    def get_stats(self):
        """Get overall statistics"""
        with self.lock:
            total_users = len(self.data)
            live_users = len(self.get_live_users())
            recording_users = len(self.get_recording_users())
            total_recordings = sum(data.get('total_recordings', 0) for data in self.data.values())
            
            return {
                'total_users': total_users,
                'live_users': live_users,
                'recording_users': recording_users,
                'total_recordings': total_recordings
            }

    def export_data(self, file_path=None):
        """Export status data to a file"""
        if not file_path:
            file_path = f"status_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with self.lock:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.data, f, indent=2, default=str)
                logger.info(f"Exported status data to {file_path}")
                return file_path
            except Exception as e:
                logger.error(f"Error exporting data: {e}")
                return None

    def import_data(self, file_path):
        """Import status data from a file"""
        try:
            with open(file_path, 'r') as f:
                imported_data = json.load(f)
            
            with self.lock:
                # Merge with existing data
                for username, data in imported_data.items():
                    if username not in self.data:
                        self.data[username] = data
                    else:
                        # Keep more recent data
                        existing_check = self.data[username].get('last_check')
                        imported_check = data.get('last_check')
                        
                        if imported_check and (not existing_check or imported_check > existing_check):
                            self.data[username] = data

                self._save_status()
                logger.info(f"Imported status data from {file_path}")
                return True
                
        except Exception as e:
            logger.error(f"Error importing data: {e}")
            return False