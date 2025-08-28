# src/utils/status_tracker.py

import threading
import time
from datetime import datetime, timedelta


class StatusTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = {}  # username -> info

    def update_status(self, username, online=False, recording=False):
        with self.lock:
            if username not in self.status:
                self.status[username] = {
                    "online": False,
                    "recording": False,
                    "last_online": None,
                    "last_duration": None,
                    "current_start": None,
                }

            user_status = self.status[username]
            user_status["online"] = online
            user_status["recording"] = recording

            if online:
                if user_status["current_start"] is None:
                    # just went online
                    user_status["current_start"] = datetime.utcnow()
            else:
                if user_status["current_start"]:
                    # just went offline, compute duration
                    duration = datetime.utcnow() - user_status["current_start"]
                    user_status["last_duration"] = str(duration).split(".")[0]  # remove microseconds
                    user_status["last_online"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    user_status["current_start"] = None

    def get_status(self):
        with self.lock:
            result = {}
            for username, info in self.status.items():
                entry = info.copy()
                # calculate current duration if live
                if info["online"] and info["current_start"]:
                    duration = datetime.utcnow() - info["current_start"]
                    entry["current_duration"] = str(duration).split(".")[0]
                else:
                    entry["current_duration"] = None
                result[username] = entry
            return result


# Singleton instance
status_tracker = StatusTracker()
