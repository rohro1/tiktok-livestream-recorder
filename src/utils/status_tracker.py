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
                        self.status = json.load(f)
                else:
                    self.status = {}
        except Exception:
            self.status = {}

    def _save_status(self):
        with self.lock:
            with open(self.status_file, 'w') as f:
                json.dump(self.status, f, indent=2)

    def update_user_status(self, username, **kwargs):
        with self.lock:
            if username not in self.status:
                self.status[username] = {}
            
            self.status[username].update({
                'last_updated': datetime.now().isoformat(),
                **kwargs
            })
            self._save_status()

    def get_user_status(self, username):
        with self.lock:
            return self.status.get(username, {})

    def get_online_users(self):
        with self.lock:
            return [user for user, data in self.status.items() 
                   if data.get('is_live', False)]