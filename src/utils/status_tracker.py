# src/utils/status_tracker.py
import threading
from datetime import datetime

class StatusTracker:
    def __init__(self):
        self._lock = threading.RLock()
        self._map = {}

    def _ensure(self, username):
        with self._lock:
            if username not in self._map:
                self._map[username] = {
                    "online": False,
                    "last_online": None,
                    "live_duration": 0,
                    "recording": False,
                    "recording_file": None,
                }
            return self._map[username]

    def get_status(self, username):
        with self._lock:
            self._ensure(username)
            return dict(self._map[username])

    def update_status(self, username, online=None, live_duration=None, recording=None):
        with self._lock:
            status = self._ensure(username)
            if online is not None:
                status["online"] = online
            if live_duration is not None:
                status["live_duration"] = live_duration
            if recording is not None:
                status["recording"] = recording

    def set_recording_file(self, username, path):
        with self._lock:
            status = self._ensure(username)
            status["recording_file"] = path

    def get_recording_file(self, username):
        with self._lock:
            status = self._ensure(username)
            return status.get("recording_file")
