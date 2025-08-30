# src/core/tiktok_recorder.py
import subprocess
import threading
import logging
import os

logger = logging.getLogger("tiktok_recorder")

class TikTokLiveRecorder:
    """
    Records a TikTok livestream via ffmpeg, saves locally.
    """

    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None

    def start_recording(self, output_path: str) -> bool:
        """
        Start recording TikTok livestream to file.
        """
        live_url = self.api.get_live_url()
        if not live_url:
            logger.warning("No live URL found for %s", self.api.username)
            return False

        logger.info("Starting ffmpeg recording for %s -> %s", self.api.username, output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",                # overwrite output
            "-i", live_url,
            "-c", "copy",
            "-t", "00:59:00",    # safeguard max 59 min per file
            output_path,
        ]

        def run_ffmpeg():
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.process.communicate()
            except Exception as e:
                logger.error("ffmpeg error for %s: %s", self.api.username, e)

        self.thread = threading.Thread(target=run_ffmpeg, daemon=True)
        self.thread.start()
        return True

    def stop_recording(self):
        """
        Stop ffmpeg recording.
        """
        if self.process and self.process.poll() is None:
            logger.info("Stopping recording for %s", self.api.username)
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self.thread = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
