from datetime import datetime, timedelta
import threading
import time

class StatusTracker:
    def __init__(self):
        self.online_users = {}
        self.last_updated = None
        self.lock = threading.Lock()
        self._start_cleanup_thread()

    def update_user_status(self, username, is_live):
        with self.lock:
            if is_live:
                self.online_users[username] = datetime.now()
            else:
                self.online_users.pop(username, None)
            self.last_updated = datetime.now()

    def get_online_users(self):
        with self.lock:
            # Remove users that haven't updated in 5 minutes
            current_time = datetime.now()
            active_users = {
                user: last_seen for user, last_seen in self.online_users.items()
                if (current_time - last_seen) < timedelta(minutes=5)
            }
            self.online_users = active_users
            return list(active_users.keys())

    def _cleanup_old_users(self):
        while True:
            self.get_online_users()  # This will clean up old users
            time.sleep(60)  # Run cleanup every minute

    def _start_cleanup_thread(self):
        cleanup_thread = threading.Thread(target=self._cleanup_old_users, daemon=True)
        cleanup_thread.start()
