import threading
import time
from src.core.tiktok_recorder import TikTokRecorder

def start_recorder_worker(status_tracker):
    def worker():
        recorder = TikTokRecorder(status_tracker)
        while True:
            recorder.check_and_record()
            time.sleep(60)  # check usernames every 60 seconds
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
