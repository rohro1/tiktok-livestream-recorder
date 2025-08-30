# src/core/tiktok_recorder.py
import os
import subprocess
import logging
import yt_dlp
from time import time

logger = logging.getLogger("tiktok-recorder")
logger.setLevel(logging.INFO)

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self.process = None
        self.start_time = None
        self.output_path = None

    def start_recording(self, output_path):
        """
        Starts recording the livestream to the specified output path using ffmpeg.
        """
        url = self.api.get_live_url()
        if not url:
            logger.error(f"{self.api.username} is not live, cannot start recording.")
            return False

        self.output_path = output_path
        ffmpeg_cmd = [
            "ffmpeg", "-i", url, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-maxrate", "1M", "-bufsize", "2M", "-s", self.resolution, "-f", "mp4", self.output_path
        ]

        try:
            logger.info(f"Starting recording for {self.api.username} at {self.output_path}")
            self.process = subprocess.Popen(ffmpeg_cmd)
            self.start_time = time()
            return True
        except Exception as e:
            logger.error(f"Error starting recording for {self.api.username}: {e}")
            return False

    def stop_recording(self):
        """
        Stops the recording process.
        """
        if self.process:
            try:
                self.process.terminate()
                self.process.wait()
                self.process = None
                logger.info(f"Stopped recording for {self.api.username}")
            except Exception as e:
                logger.error(f"Error stopping recording for {self.api.username}: {e}")
        if self.output_path:
            logger.info(f"Saved recording for {self.api.username} at {self.output_path}")
        self.output_path = None

    def is_running(self):
        """
        Checks if the recording process is still running.
        """
        if self.process:
            return self.process.poll() is None
        return False
