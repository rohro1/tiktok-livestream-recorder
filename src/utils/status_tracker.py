# src/utils/status_tracker.py
import threading
from datetime import datetime

class StatusTracker:
    def __init__(self):
        self._lock = threading.RLock()
        self._map = {}  # username -> dict

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
            st = self._ensure(username)
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            if online is not None:
                if online:
                    st["online"] = True
                    st["last_online"] = now
                else:
                    st["online"] = False
            if live_duration is not None:
                st["live_duration"] = live_duration
            if recording is not None:
                st["recording"] = recording

    def set_recording_file(self, username, path):
        with self._lock:
            st = self._ensure(username)
            st["recording_file"] = path

    def get_recording_file(self, username):
        with self._lock:
            st = self._ensure(username)
            return st.get("recording_file")

    # ✅ Fix for your error
    def get_all(self):
        """Return a shallow copy of all user statuses"""
        with self._lock:
            return {username: dict(info) for username, info in self._map.items()}
