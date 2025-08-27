from datetime import datetime

class StatusTracker:
    def __init__(self):
        self.data = {}

    def initialize(self, username):
        self.data[username] = {
            "online": False,
            "recording": False,
            "recording_start": None,
            "last_seen": None,
            "last_duration_minutes": None
        }

    def set_online(self, username, online=True):
        self.data[username]["online"] = online
        if online:
            self.data[username]["last_seen"] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    def set_offline(self, username, online=False):
        self.data[username]["online"] = online
        self.data[username]["recording"] = False
        if not online and self.data[username]["recording_start"]:
            start = datetime.strptime(self.data[username]["recording_start"], "%a, %d %b %Y %H:%M:%S GMT")
            duration = (datetime.utcnow() - start).seconds // 60
            self.data[username]["last_duration_minutes"] = duration
        self.data[username]["recording_start"] = None

    def start_recording(self, username):
        self.data[username]["recording"] = True
        self.data[username]["recording_start"] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    def stop_recording(self, username):
        self.data[username]["recording"] = False

    def is_recording(self, username):
        return self.data[username]["recording"]

    def get_all_status(self):
        return self.data

tracker = StatusTracker()
