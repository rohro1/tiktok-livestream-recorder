import datetime

class StatusTracker:
    def __init__(self):
        self.status = {}

    def update(self, username, online, recording):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if username not in self.status:
            self.status[username] = {
                "online": online,
                "recording": recording,
                "last_online": now if online else "",
                "last_duration": ""
            }
        else:
            data = self.status[username]
            if online:
                if not data["online"]:
                    data["last_online"] = now
                data["online"] = True
                data["recording"] = recording
            else:
                if data["online"]:
                    data["last_duration"] = f"Ended at {now}"
                data["online"] = False
                data["recording"] = recording

status_tracker = StatusTracker()
