import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class StatusTracker:
    def __init__(self):
        self._status = {}
        self._lock = threading.Lock()
        
    def update_status(self, username: str, live_status: str, recording_status: str, 
                     stream_url: str = None, recording_file: str = None):
        """Update user status thread-safely"""
        with self._lock:
            if username not in self._status:
                self._status[username] = {
                    'username': username,
                    'live_status': 'offline',
                    'recording_status': 'idle',
                    'last_online': None,
                    'recording_started': None,
                    'recording_duration': 0,
                    'stream_url': None,
                    'recording_file': None,
                    'last_checked': datetime.now(),
                    'error_count': 0
                }
            
            # Update status
            old_status = self._status[username]['live_status']
            self._status[username]['live_status'] = live_status
            self._status[username]['recording_status'] = recording_status
            self._status[username]['last_checked'] = datetime.now()
            
            # Update last online time
            if live_status == 'live':
                if old_status != 'live':
                    self._status[username]['last_online'] = datetime.now()
                    self._status[username]['recording_started'] = datetime.now()
                    logger.info(f"{username} went live at {self._status[username]['last_online']}")
                
                # Update recording duration for live users
                if self._status[username]['recording_started']:
                    duration = datetime.now() - self._status[username]['recording_started']
                    self._status[username]['recording_duration'] = int(duration.total_seconds())
            
            elif live_status == 'offline' and old_status == 'live':
                # User went offline
                self._status[username]['recording_started'] = None
                self._status[username]['recording_duration'] = 0
                logger.info(f"{username} went offline")
            
            # Update stream info
            if stream_url:
                self._status[username]['stream_url'] = stream_url
            if recording_file:
                self._status[username]['recording_file'] = recording_file
                
            # Reset error count on successful update
            if live_status != 'error':
                self._status[username]['error_count'] = 0
            else:
                self._status[username]['error_count'] += 1
    
    def get_status(self, username: str) -> Dict[str, Any]:
        """Get status for a specific user"""
        with self._lock:
            if username not in self._status:
                return {
                    'username': username,
                    'live_status': 'unknown',
                    'recording_status': 'idle',
                    'last_online': None,
                    'recording_started': None,
                    'recording_duration': 0,
                    'stream_url': None,
                    'recording_file': None,
                    'last_checked': None,
                    'error_count': 0
                }
            
            status = self._status[username].copy()
            
            # Update recording duration for currently live users
            if status['live_status'] == 'live' and status['recording_started']:
                duration = datetime.now() - status['recording_started']
                status['recording_duration'] = int(duration.total_seconds())
            
            # Format timestamps for display
            if status['last_online']:
                status['last_online_formatted'] = status['last_online'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                status['last_online_formatted'] = 'Never'
            
            if status['last_checked']:
                status['last_checked_formatted'] = status['last_checked'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                status['last_checked_formatted'] = 'Never'
            
            # Format recording duration
            if status['recording_duration'] > 0:
                hours = status['recording_duration'] // 3600
                minutes = (status['recording_duration'] % 3600) // 60
                seconds = status['recording_duration'] % 60
                status['recording_duration_formatted'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                status['recording_duration_formatted'] = "00:00:00"
            
            return status
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all users"""
        with self._lock:
            result = {}
            for username in self._status:
                result[username] = self.get_status(username)
            return result
    
    def remove_user(self, username: str):
        """Remove a user from tracking"""
        with self._lock:
            if username in self._status:
                del self._status[username]
                logger.info(f"Removed {username} from status tracking")
    
    def get_live_users(self) -> list:
        """Get list of currently live users"""
        with self._lock:
            live_users = []
            for username, status in self._status.items():
                if status['live_status'] == 'live':
                    live_users.append(username)
            return live_users
    
    def cleanup_old_entries(self, max_age_hours: int = 24):
        """Remove old entries that haven't been updated recently"""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            to_remove = []
            
            for username, status in self._status.items():
                if status['last_checked'] and status['last_checked'] < cutoff_time:
                    to_remove.append(username)
            
            for username in to_remove:
                del self._status[username]
                logger.info(f"Cleaned up old entry for {username}")
    
    def mark_error(self, username: str, error_message: str):
        """Mark a user as having an error"""
        self.update_status(username, 'error', f'Error: {error_message[:100]}')
    
    def is_being_monitored(self, username: str) -> bool:
        """Check if a user is currently being monitored"""
        with self._lock:
            if username not in self._status:
                return False
            
            # Consider a user monitored if checked within last 2 minutes
            last_checked = self._status[username]['last_checked']
            if last_checked:
                time_diff = datetime.now() - last_checked
                return time_diff.total_seconds() < 120
            
            return False