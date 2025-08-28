import os
import threading
import time
from datetime import datetime
from src.utils.google_drive_uploader import upload_file
from src.core.tiktok_api import TikTokAPI

class TikTokRecorder:
    def __init__(self, username, drive_service=None):
        self.username = username
        self.drive_service = drive_service
        self._recording = False
        self.last_seen = None
        self._stop_event = threading.Event()
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.api = TikTokAPI(username)

        self.recording_start_time = None
        self.current_file = None

    def start(self):
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if self._recording:
            self._stop_recording()

    def is_live(self):
        return self.api.is_live()

    def is_recording(self):
        return self._recording

    def current_duration(self):
        if self._recording and self.recording_start_time:
            return int(time.time() - self.recording_start_time)
        return 0

    def _monitor(self):
        while not self._stop_event.is_set():
            live = self.is_live()
            if live and not self._recording:
                self._start_recording()
            elif not live and self._recording:
                self._stop_recording()
            if live:
                self.last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            time.sleep(30)

    def _start_recording(self):
        date_folder = datetime.now().strftime("%m-%d-%Y")
        save_dir = os.path.join("recordings", self.username, date_folder)
        os.makedirs(save_dir, exist_ok=True)
        count = 1
        filename = f"{self.username}-{count}.mp4"
        filepath = os.path.join(save_dir, filename)
        while os.path.exists(filepath):
            count += 1
            filename = f"{self.username}-{count}.mp4"
            filepath = os.path.join(save_dir, filename)
        self.current_file = filepath

        self._recording = True
        self.recording_start_time = time.time()
        threading.Thread(target=self._record_livestream, daemon=True).start()

    def _record_livestream(self):
        url = self.api.get_livestream_url()
        cmd = f"ffmpeg -y -i \"{url}\" -c copy -t 00:30:00 \"{self.current_file}\""
        os.system(cmd)  # Simple blocking call for recording
        if self.drive_service:
            upload_file(self.drive_service, self.current_file, self.username)
        self._recording = False
        self.recording_start_time = None
        self.current_file = None

    def _stop_recording(self):
        # ffmpeg will naturally stop after 30 mins, or you can add kill logic
        self._recording = False
        self.recording_start_time = None
        self.current_file = None
