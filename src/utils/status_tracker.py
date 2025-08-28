# src/utils/status_tracker.py

import threading
import time
from datetime import datetime

class StatusTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = {}

    def set_online(self, username: str):
        with self.lock:
            if username not in self.status:
                self.status[username] = {}
            self.status[username]["online"] = True
            self.status[username]["recording"] = True
            self.status[username]["start_time"] = datetime.utcnow()
            self.status[username]["last_online"] = datetime.utcnow()
            self.status[username]["duration"] = "0s"

    def set_offline(self, username: str):
        with self.lock:
            if username not in self.status:
                self.status[username] = {}
            self.status[username]["online"] = False
            self.status[username]["recording"] = False
            if "start_time" in self.status[username]:
                live_time = datetime.utcnow() - self.status[username]["start_time"]
                self.status[username]["duration"] = str(live_time).split(".")[0]
            self.status[username]["last_online"] = datetime.utcnow()

    def update_duration(self, username: str):
        with self.lock:
            if username in self.status and self.status[username].get("online") and "start_time" in self.status[username]:
                live_time = datetime.utcnow() - self.status[username]["start_time"]
                self.status[username]["duration"] = str(live_time).split(".")[0]

    def get_status(self):
        with self.lock:
            for user in self.status.keys():
                self.update_duration(user)
            return self.status.copy()
