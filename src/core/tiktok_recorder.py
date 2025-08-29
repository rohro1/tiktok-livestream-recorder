# tiktok_recorder.py
import subprocess
import threading
import os
from src.utils.status_tracker import status_tracker
from datetime import datetime
from TikTokLiveRecorder.src.core.tiktok_api import TikTokAPI

class TikTokLiveRecorder:
    """
    Records TikTok livestream using ffmpeg at 480p
    """
    def __init__(self, api: TikTokAPI, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self.recording_thread = None
        self.stop_flag = threading.Event()
        self.output_path = None

    def start_recording(self, output_path):
        self.output_path = output_path
        self.stop_flag.clear()
        self.recording_thread = threading.Thread(target=self._record)
        self.recording_thread.start()

    def _record(self):
        stream_url = self.api.get_stream_url()
        if not stream_url:
            print(f"[TikTokLiveRecorder] No livestream URL for {self.api.username}")
            return

        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", stream_url,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "1000k",
            "-s", "640x480",  # 480p
            "-c:a", "aac",
            "-y",
            self.output_path
        ]

        print(f"[TikTokLiveRecorder] Recording {self.api.username} to {self.output_path}")
        try:
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            start_time = datetime.now()
            while process.poll() is None and not self.stop_flag.is_set():
                elapsed = int((datetime.now() - start_time).total_seconds())
                status_tracker.update(
                    self.api.username,
                    online=True,
                    recording_duration=elapsed,
                    last_online=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                threading.Event().wait(5)
            if process.poll() is None:
                process.terminate()
        except Exception as e:
            print(f"[TikTokLiveRecorder] Error recording {self.api.username}: {e}")

    def stop_recording(self):
        self.stop_flag.set()
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join()
        status_tracker.update(self.api.username, online=False)
