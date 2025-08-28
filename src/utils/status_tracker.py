# src/utils/status_tracker.py

import threading
from datetime import datetime

class StatusTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.statuses = {}  # {username: {"online": bool, "recording": bool, "start_time": datetime, "last_online": datetime, "duration": int}}

    def set_online(self, username):
        with self.lock:
            now = datetime.now()
            if username not in self.statuses:
                self.statuses[username] = {}
            self.statuses[username]["online"] = True
            self.statuses[username]["recording"] = True
            self.statuses[username]["start_time"] = now
            self.statuses[username]["last_online"] = now
            self.statuses[username]["duration"] = 0

    def set_offline(self, username):
        with self.lock:
            now = datetime.now()
            if username not in self.statuses:
                self.statuses[username] = {}
            self.statuses[username]["online"] = False
            self.statuses[username]["recording"] = False
            self.statuses[username]["last_online"] = now
            start_time = self.statuses[username].get("start_time")
            if start_time:
                self.statuses[username]["duration"] = int((now - start_time).total_seconds())

    def get_status(self):
        with self.lock:
            # Return a copy to avoid threading issues
            return {u: s.copy() for u, s in self.statuses.items()}

# Singleton instance for main.py
status_tracker = StatusTracker()
