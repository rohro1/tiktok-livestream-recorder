import threading
import time

class StatusTracker:
    def __init__(self):
        self.status = {}
        self.lock = threading.Lock()

    def set_status(self, username, online=False, recording=False):
        with self.lock:
            self.status[username] = {
                "status": "online" if online else "offline",
                "recording": recording,
                "last_live": time.strftime("%Y-%m-%d %H:%M:%S") if online else self.status.get(username, {}).get("last_live"),
                "duration": self._calculate_duration(username, online)
            }

    def _calculate_duration(self, username, online):
        if online:
            if "start_time" not in self.status.get(username, {}):
                self.status[username]["start_time"] = time.time()
            elapsed = time.time() - self.status[username]["start_time"]
            return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        else:
            if "start_time" in self.status.get(username, {}):
                del self.status[username]["start_time"]
            return "0m 0s"

    def get_status(self, username):
        with self.lock:
            return self.status.get(username, {"status": "unknown", "recording": False, "last_live": None, "duration": None})

    def get_all_status(self):
        with self.lock:
            return dict(self.status)

# Singleton tracker
status_tracker = StatusTracker()
