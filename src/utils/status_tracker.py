from datetime import datetime
import threading
import json
import os

class StatusTracker:
    def __init__(self):
        self.status_file = "status.json"
        self.lock = threading.Lock()
        self._load_status()

    def _load_status(self):
        try:
            with self.lock:
                if os.path.exists(self.status_file):
                    with open(self.status_file, 'r') as f:
                        data = json.load(f)
                        self.status = data.get('statuses', {})
                        self.last_checks = {
                            k: datetime.fromisoformat(v) 
                            for k, v in data.get('last_checks', {}).items()
                        }
                else:
                    self._save_status()
        except Exception as e:
            print(f"Error initializing status file: {e}")
            self.status = {}
            self.last_checks = {}
            self._save_status()

    def _save_status(self):
        with self.lock:
            data = {
                'statuses': self.status,
                'last_checks': {
                    k: v.isoformat() 
                    for k, v in self.last_checks.items()
                }
            }
            with open(self.status_file, 'w') as f:
                json.dump(data, f)

    def update_user_status(self, username, **kwargs):
        with self.lock:
            if username not in self.status:
                self.status[username] = {}
            
            # Update with current timestamp
            current_time = datetime.now().isoformat()
            
            # Handle special cases for live status
            if 'is_live' in kwargs:
                self.status[username]['is_live'] = bool(kwargs['is_live'])
                if kwargs['is_live']:
                    self.status[username]['last_seen_live'] = current_time
            
            # Update status with all provided fields
            self.status[username].update({
                'last_updated': current_time,
                **kwargs
            })
            
            self.last_checks[username] = datetime.now()
            self._save_status()

    def get_user_status(self, username):
        """Get user status with proper boolean values"""
        with self.lock:
            status = self.status.get(username, {}).copy()
            # Ensure boolean fields are proper Python booleans
            status['is_live'] = bool(status.get('is_live', False))
            status['is_recording'] = bool(status.get('is_recording', False))
            
            # Add formatted timestamps
            try:
                if 'last_updated' in status:
                    last_updated = datetime.fromisoformat(status['last_updated'])
                    status['last_updated_formatted'] = last_updated.strftime('%Y-%m-%d %H:%M:%S')
                if 'last_seen_live' in status:
                    last_seen = datetime.fromisoformat(status['last_seen_live'])
                    status['last_seen_formatted'] = last_seen.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
            
            return status

    def get_online_users(self):
        with self.lock:
            return [user for user, data in self.status.items() 
                   if data.get('is_live', False)]

    def has_recent_checks(self, max_age_seconds=300):  # 5 minutes
        """Check if we have recent status checks"""
        with self.lock:
            if not self.last_checks:
                return False
            now = datetime.now().timestamp()
            return any(
                (now - timestamp) < max_age_seconds 
                for timestamp in self.last_checks.values()
            )

    def get_all_statuses(self):
        with self.lock:
            return self.status.copy()