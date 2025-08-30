import subprocess
import threading
import os
import logging
import tempfile
from utils.google_drive_uploader import GoogleDriveUploader

logger = logging.getLogger("tiktok-recorder")

class TikTokLiveRecorder:
    def __init__(self, api, uploader: GoogleDriveUploader, resolution="480p"):
        self.api = api
        self.uploader = uploader
        self.resolution = resolution
        self.proc = None
        self.thread = None
        self.running = False
        self.tmpfile = None

    def start_recording(self):
        live_url = self.api.get_live_url()
        if not live_url:
            logger.warning("%s is not live, skipping recording", self.api.username)
            return False

        fd, self.tmpfile = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", live_url,
            "-c", "copy",
            "-f", "mp4",
            self.tmpfile,
        ]
        logger.info("Recording started for %s → %s", self.api.username, self.tmpfile)

        def run_ffmpeg():
            try:
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self.proc.wait()
            finally:
                self.running = False
                if self.tmpfile and os.path.exists(self.tmpfile):
                    try:
                        remote_name = os.path.basename(self.tmpfile)
                        self.uploader.upload_file(
                            self.tmpfile,
                            remote_subfolder=self.api.username,
                            remote_name=remote_name,
                        )
                        os.remove(self.tmpfile)
                        logger.info("Uploaded and cleaned up %s", self.tmpfile)
                    except Exception as e:
                        logger.error("Upload failed for %s: %s", self.api.username, e)

        self.thread = threading.Thread(target=run_ffmpeg, daemon=True)
        self.thread.start()
        self.running = True
        return True

    def stop_recording(self):
        if self.proc and self.running:
            logger.info("Stopping recording for %s", self.api.username)
            self.proc.terminate()
            self.proc.wait()
            self.running = False

    def is_running(self):
        return self.running
