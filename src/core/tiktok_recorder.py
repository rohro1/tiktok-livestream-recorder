# TikTokLiveRecorder/src/core/tiktok_recorder.py
import subprocess
import threading
import time

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self.recording = False
        self._process = None

    def start_recording(self, output_path):
        """Start recording livestream in a separate thread"""
        if not self.api.is_live():
            print(f"{self.api.username} is not live.")
            return
        live_url = self.api.get_live_url()
        if not live_url:
            print(f"No live URL for {self.api.username}")
            return

        self.recording = True
        threading.Thread(target=self._record, args=(live_url, output_path), daemon=True).start()

    def _record(self, live_url, output_path):
        """Use ffmpeg to record livestream at 480p"""
        try:
            command = [
                "ffmpeg",
                "-y",
                "-i", live_url,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-tune", "zerolatency",
                "-vf", "scale=-2:480",
                "-c:a", "aac",
                "-b:a", "128k",
                "-f", "mp4",
                output_path
            ]
            self._process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._process.wait()
        except Exception as e:
            print(f"Error recording {self.api.username}: {e}")
        finally:
            self.recording = False

    def stop_recording(self):
        """Stop recording livestream"""
        if self._process:
            self._process.terminate()
            self._process = None
        self.recording = False
