import threading

class StatusTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def update_user(self, username, online=False, recording_duration=0, last_online=None, live_duration=0):
        with self._lock:
            self._data[username] = {
                "online": online,
                "recording_duration": recording_duration,
                "last_online": last_online,
                "live_duration": live_duration
            }

    def get_status(self):
        with self._lock:
            return self._data.copy()
