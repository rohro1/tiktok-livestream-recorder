import subprocess
import threading
import logging

logger = logging.getLogger("tiktok-recorder")

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self.proc = None
        self.thread = None
        self._running = False

    def is_running(self):
        return self._running and self.proc and self.proc.poll() is None

    def start_recording(self, output_path):
        stream_url = self.api.get_stream_url()
        if not stream_url:
            logger.warning("No stream URL found for %s", self.api.username)
            return False

        cmd = [
            "ffmpeg",
            "-y",
            "-i", stream_url,
            "-c", "copy",
            "-f", "mp4",
            output_path,
        ]

        def run():
            logger.info("Recording started for %s → %s", self.api.username, output_path)
            self._running = True
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.proc.wait()
            except Exception as e:
                logger.error("Recording error: %s", e)
            finally:
                self._running = False
                logger.info("Recording stopped for %s", self.api.username)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return True

    def stop_recording(self):
        if self.proc and self.is_running():
            self.proc.terminate()
            logger.info("Terminated recording for %s", self.api.username)
            self._running = False
