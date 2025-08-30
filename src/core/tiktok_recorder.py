# src/core/tiktok_recorder.py
import subprocess
import threading
import shlex
import logging
import os

logger = logging.getLogger("tiktok_recorder")

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")  # if you bundle a static ffmpeg, set env var to its path

class TikTokLiveRecorder:
    """
    Simple wrapper around ffmpeg to record a live HLS/DASH stream URL to a local file.
    The recorder writes to a temporary file path and exposes is_running(), start_recording(), stop_recording().
    """
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.proc = None
        self.lock = threading.Lock()

    def is_running(self) -> bool:
        with self.lock:
            return self.proc is not None and self.proc.poll() is None

    def start_recording(self, out_path: str, resolution: str = "480p") -> bool:
        if not self.stream_url:
            logger.warning("No stream_url provided to recorder (will still attempt to run ffmpeg to probe).")
        # ffmpeg command: read input (stream_url) and transcode to mp4 at ~480p
        ffmpeg_cmd = [
            FFMPEG_BIN,
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
            "-i", self.stream_url or "pipe:"),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-maxrate", "1000k",
            "-bufsize", "2000k",
            "-vf", "scale=-2:480",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "mp4",
            out_path
        ]
        # Python lists -> shell exec
        try:
            with self.lock:
                # if ffmpeg binary not present, this will raise FileNotFoundError
                self.proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Started ffmpeg (pid=%s) -> %s", self.proc.pid if self.proc else None, out_path)
            return True
        except FileNotFoundError:
            logger.exception("ffmpeg binary not found. Set FFMPEG_BIN env to a valid ffmpeg binary or include ffmpeg in image.")
            return False
        except Exception:
            logger.exception("Failed to start ffmpeg")
            return False

    def stop_recording(self):
        with self.lock:
            if not self.proc:
                return
            try:
                self.proc.terminate()
                self.proc.wait(timeout=15)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
            logger.info("Stopped ffmpeg recording")
