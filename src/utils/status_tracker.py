# src/utils/status_tracker.py
import threading
from datetime import datetime

class StatusTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def update_status(self, username, online=None, recording=None):
        with self._lock:
            if username not in self._data:
                self._data[username] = {
                    "last_online": "N/A",
                    "live_duration": 0,
                    "online": False,
                    "recording_duration": 0,
                    "recording": False,
                    "recording_file": None,
                }
            entry = self._data[username]

            if online is not None:
                entry["online"] = online
                if online:
                    entry["last_online"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            if recording is not None:
                entry["recording"] = recording

    def set_recording_file(self, username, filepath):
        with self._lock:
            if username in self._data:
                self._data[username]["recording_file"] = filepath

    def get_recording_file(self, username):
        with self._lock:
            return self._data.get(username, {}).get("recording_file")

    def get_status(self, username):
        with self._lock:
            return self._data.get(username, {})

    # ✅ This is the method your main.py expects
    def get_all(self):
        with self._lock:
            return dict(self._data)
