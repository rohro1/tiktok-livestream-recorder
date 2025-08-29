# src/utils/status_tracker.py

class StatusTracker:
    def __init__(self):
        self._statuses = {}

    def update(self, username, last_online=None, live_duration=None, online=None, recording_duration=None):
        if username not in self._statuses:
            self._statuses[username] = {
                "last_online": last_online or "N/A",
                "live_duration": live_duration or 0,
                "online": online or False,
                "recording_duration": recording_duration or 0
            }
        else:
            if last_online is not None:
                self._statuses[username]["last_online"] = last_online
            if live_duration is not None:
                self._statuses[username]["live_duration"] = live_duration
            if online is not None:
                self._statuses[username]["online"] = online
            if recording_duration is not None:
                self._statuses[username]["recording_duration"] = recording_duration

    def get_statuses(self):
        return self._statuses

    def get(self, username, default=None):
        return self._statuses.get(username, default)

status_tracker = StatusTracker()
