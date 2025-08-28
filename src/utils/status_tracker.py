import threading

class StatusTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = {}

    def update_status(self, username, online=False, recording_duration="--", last_online="--", last_duration="--"):
        with self.lock:
            self.status[username] = {
                "online": online,
                "recording_duration": recording_duration,
                "last_online": last_online,
                "last_duration": last_duration,
            }

    def get_status(self, username):
        with self.lock:
            return self.status.get(username, {
                "online": False,
                "recording_duration": "--",
                "last_online": "--",
                "last_duration": "--"
            })

    def get_all_statuses(self):
        with self.lock:
            return dict(self.status)
