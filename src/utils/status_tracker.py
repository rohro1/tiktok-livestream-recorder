from datetime import datetime

class StatusTracker:
    def __init__(self):
        self.status = {}

    def update_status(self, username, online=False, recording=False):
        st = self.status.get(username, {})
        st["online"] = online
        st["recording"] = recording
        if online:
            st["last_online"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self.status[username] = st

    def set_recording_file(self, username, path):
        st = self.status.get(username, {})
        st["recording_file"] = path
        self.status[username] = st

    def get_recording_file(self, username):
        return self.status.get(username, {}).get("recording_file")

    def get_status(self, username):
        return self.status.get(username, {})
