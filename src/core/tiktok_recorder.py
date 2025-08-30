# src/core/tiktok_recorder.py
import subprocess
import threading
import logging
from time import time

logger = logging.getLogger("tiktok_recorder")
logger.setLevel(logging.INFO)

FFMPEG_BIN = "ffmpeg"  # assumes ffmpeg is in PATH
YT_DLP_CMD = "yt-dlp"  # assumes yt-dlp CLI is installed

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self._proc = None
        self._thread = None
        self._running = False
        self.start_time = None
        self.output_file = None

    def is_running(self):
        return self._running

    def _record_thread(self, url, output_file):
        self.start_time = time()
        self.output_file = output_file
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-i", url,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-r", "30",
            "-s", self.resolution,
            "-c:a", "aac",
            "-b:a", "128k",
            output_file
        ]
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._proc.wait()
        except Exception:
            logger.exception("Recording process failed")
        finally:
            self._running = False
            self._proc = None

    def start_recording(self, output_file):
        """
        Starts recording if user is live.
        Returns True if recording started, False if user is offline.
        """
        if not self.api.is_live():
            return False  # silently skip offline users
        live_url = self.api.get_live_url()
        if not live_url:
            return False  # URL not available yet
        self._running = True
        self._thread = threading.Thread(target=self._record_thread, args=(live_url, output_file), daemon=True)
        self._thread.start()
        logger.info("Started recording %s -> %s", self.api.username, output_file)
        return True

    def stop_recording(self):
        if self._proc:
            self._proc.terminate()
        self._running = False
