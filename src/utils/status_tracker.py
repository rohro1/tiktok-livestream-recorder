# src/utils/status_tracker.py

import threading
from datetime import datetime

class StatusTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.users = {}

    def init_users(self, usernames):
        with self.lock:
            for username in usernames:
                if username not in self.users:
                    self.users[username] = {
                        "online": False,
                        "recording_duration": 0,
                        "last_online": None,
                        "live_duration": 0
                    }

    def update_status(self, username, online):
        with self.lock:
            if username not in self.users:
                self.init_users([username])
            user = self.users[username]
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if online:
                if not user["online"]:
                    user["last_online"] = now
                    user["recording_duration"] = 0
                    user["live_duration"] = 0
                user["online"] = True
                user["recording_duration"] += 1
                user["live_duration"] += 1
            else:
                user["online"] = False
                if user["last_online"] is None:
                    user["last_online"] = now

    def get_status(self):
        with self.lock:
            return self.users.copy()


# Create a singleton instance to use in main.py
status_tracker = StatusTracker()
