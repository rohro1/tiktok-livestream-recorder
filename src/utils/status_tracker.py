import threading
from datetime import datetime, timedelta

class StatusTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._status = {}

    def update_status(self, username, online=False, recording_time=None):
        with self._lock:
            if username not in self._status:
                self._status[username] = {
                    "online": False,
                    "current_recording": None,
                    "last_online": None,
                    "last_duration": None
                }
            user_status = self._status[username]
            user_status["online"] = online
            if online and recording_time is not None:
                user_status["current_recording"] = str(recording_time)
            elif not online:
                # Save last recording duration
                if user_status["current_recording"] is not None:
                    user_status["last_duration"] = user_status["current_recording"]
                user_status["current_recording"] = None
                user_status["last_online"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_all_status(self):
        with self._lock:
            return dict(self._status)
