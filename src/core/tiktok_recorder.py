# src/core/tiktok_recorder.py
import threading
import subprocess
import logging
from time import sleep

logger = logging.getLogger("TikTokLiveRecorder")
logger.setLevel(logging.INFO)

FFMPEG_BIN = "ffmpeg"

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self.proc = None
        self._running = False
        self.lock = threading.RLock()

    def is_running(self):
        with self.lock:
            return self._running

    def start_recording(self, output_path):
        """
        Start recording the live stream.
        """
        with self.lock:
            url = self.api.get_stream_url()
            if not url:
                logger.info("No live stream URL for %s", self.api.username)
                return False
            cmd = [
                FFMPEG_BIN,
                "-i", url,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-tune", "zerolatency",
                "-vf", f"scale=-2:480",
                "-c:a", "aac",
                "-b:a", "128k",
                "-y",
                output_path
            ]
            try:
                self.proc = subprocess.Popen(cmd)
                self._running = True
                logger.info("Started recording %s to %s", self.api.username, output_path)
                return True
            except Exception:
                logger.exception("Failed to start ffmpeg for %s", self.api.username)
                self._running = False
                return False

    def stop_recording(self):
        """
        Stop the ffmpeg process.
        """
        with self.lock:
            if self.proc and self._running:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=10)
                except Exception:
                    self.proc.kill()
                self._running = False
                logger.info("Stopped recording %s", self.api.username)
