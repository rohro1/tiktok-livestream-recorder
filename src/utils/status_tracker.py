# src/utils/status_tracker.py
from threading import Lock
from datetime import datetime

class StatusTracker:
    """
    Minimal thread-safe status tracker.
    Stored per-username dict with fields:
      - online (bool)
      - recording (bool)
      - last_online (iso timestamp)
      - live_start (datetime or None)
      - live_duration (seconds)
      - recording_file (path or None)
    """
    def __init__(self):
        self._data = {}
        self._lock = Lock()

    def _ensure(self, username):
        if username not in self._data:
            self._data[username] = {
                "online": False,
                "recording": False,
                "last_online": None,
                "live_start": None,
                "live_duration": 0,
                "recording_file": None,
            }

    def update_status(self, username, online=False, recording=None):
        with self._lock:
            self._ensure(username)
            entry = self._data[username]
            if online and not entry["online"]:
                entry["live_start"] = datetime.utcnow()
            if not online and entry["online"]:
                entry["last_online"] = datetime.utcnow().isoformat()
                entry["live_start"] = None
                entry["live_duration"] = 0
            entry["online"] = online
            if recording is not None:
                entry["recording"] = bool(recording)

    def set_recording_file(self, username, path):
        with self._lock:
            self._ensure(username)
            self._data[username]["recording_file"] = path

    def get_recording_file(self, username):
        with self._lock:
            self._ensure(username)
            return self._data[username]["recording_file"]

    def update_live_duration(self, username):
        with self._lock:
            self._ensure(username)
            entry = self._data[username]
            if entry["live_start"]:
                delta = datetime.utcnow() - entry["live_start"]
                entry["live_duration"] = int(delta.total_seconds())

    def get_status(self, username):
        with self._lock:
            self._ensure(username)
            d = dict(self._data[username])
            # format times as iso strings
            if d["live_start"]:
                d["live_start"] = d["live_start"].isoformat()
            return d
