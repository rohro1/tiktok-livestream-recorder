import subprocess
import threading
import logging

logger = logging.getLogger("recorder")

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self._process = None
        self._thread = None

    def start_recording(self, out_path):
        stream_url = self.api.get_stream_url()
        if not stream_url:
            logger.warning("No live stream URL for %s", self.api.username)
            return False

        cmd = [
            "ffmpeg",
            "-y",
            "-i", stream_url,
            "-c", "copy",
            "-t", "00:04:00",  # safety cutoff, prevent infinite stuck
            out_path
        ]

        def run():
            logger.info("Recording %s -> %s", self.api.username, out_path)
            self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._process.communicate()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def stop_recording(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            logger.info("Stopped recording %s", self.api.username)

    def is_running(self):
        return self._process and self._process.poll() is None
