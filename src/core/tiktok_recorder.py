"""
src/core/tiktok_recorder.py

Records a TikTok live stream (480p) by resolving the stream URL (via TikTokAPI/yt-dlp)
and invoking ffmpeg to record/encode to MP4.

API:
    recorder = TikTokLiveRecorder(api: TikTokAPI, resolution="480p")
    recorder.start_recording(output_path="/path/to/out.mp4")
    recorder.stop_recording()
"""

import subprocess
import shlex
import threading
import time
import os
import logging

logger = logging.getLogger("tiktok-recorder")
logger.setLevel(logging.INFO)

FFMPEG_BIN = "ffmpeg"  # ensure ffmpeg is in PATH

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p", video_bitrate="800k", audio_bitrate="128k"):
        """
        api: instance of TikTokAPI
        resolution: string like '480p' (we map to height 480)
        """
        self.api = api
        self.resolution = resolution
        self.proc = None
        self._lock = threading.Lock()
        self._running = False
        self.video_bitrate = video_bitrate
        self.audio_bitrate = audio_bitrate

    def _resolution_to_height(self):
        if self.resolution.endswith("p"):
            try:
                return int(self.resolution[:-1])
            except Exception:
                return 480
        return 480

    def _build_ffmpeg_cmd(self, stream_url, output_path, duration=None):
        """
        Build ffmpeg command line to read stream_url and record at 480p.
        We re-encode to ensure consistent mp4 container.
        """
        height = self._resolution_to_height()
        # Use libx264 with reasonable settings for 480p
        # -y : overwrite
        # -hide_banner -loglevel warning : quieter output
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
            "-i", stream_url,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", self.video_bitrate,
            "-maxrate", "900k",
            "-bufsize", "1600k",
            "-vf", f"scale=-2:{height}",
            "-c:a", "aac",
            "-b:a", self.audio_bitrate,
            "-f", "mp4",
            output_path
        ]
        # If duration specified, add -t <duration>
        if duration:
            cmd.insert(3, "-t")
            cmd.insert(4, str(duration))
        return cmd

    def start_recording(self, output_path, max_retries=3):
        """
        Start recording to output_path. This spawns ffmpeg in background (thread-safe).
        Blocks until ffmpeg process is launched.
        """
        with self._lock:
            if self._running:
                logger.info("Recorder already running for %s", self.api.username)
                return False

            # attempt to obtain stream URL
            stream_url = self.api.get_stream_url()
            if not stream_url:
                logger.warning("Could not resolve stream URL for %s", self.api.username)
                return False

            # ensure output directory exists
            outdir = os.path.dirname(output_path)
            if outdir:
                os.makedirs(outdir, exist_ok=True)

            cmd = self._build_ffmpeg_cmd(stream_url, output_path)
            logger.info("Starting ffmpeg for %s: %s", self.api.username, " ".join(shlex.quote(p) for p in cmd))

            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                # optionally spin a thread to log ffmpeg stderr
                threading.Thread(target=self._drain_ffmpeg_stderr, args=(self.proc.stderr,), daemon=True).start()
                self._running = True
                # small sleep to allow process to fail early if stream invalid
                time.sleep(1.5)
                if self.proc.poll() is not None:
                    # process exited quickly (error)
                    stderr = self.proc.stderr.read() if self.proc.stderr else ""
                    logger.error("ffmpeg exited immediately for %s — stderr: %s", self.api.username, stderr)
                    self._running = False
                    return False
                logger.info("ffmpeg started (pid=%s) for %s", getattr(self.proc, "pid", "?"), self.api.username)
                return True
            except Exception as e:
                logger.exception("Failed to start ffmpeg for %s: %s", self.api.username, e)
                self._running = False
                return False

    def _drain_ffmpeg_stderr(self, stderr_pipe):
        try:
            for line in stderr_pipe:
                if line:
                    logger.debug("ffmpeg: %s", line.strip())
        except Exception:
            pass

    def stop_recording(self, timeout=10):
        """
        Stop ffmpeg process gracefully. If not stopped in 'timeout' seconds, kill it.
        """
        with self._lock:
            if not self._running or self.proc is None:
                return True
            try:
                logger.info("Stopping ffmpeg (pid=%s) for %s", getattr(self.proc, "pid", "?"), self.api.username)
                # send SIGINT for graceful finish
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("ffmpeg did not exit in time; killing")
                    self.proc.kill()
                    self.proc.wait(timeout=5)
                logger.info("ffmpeg stopped for %s", self.api.username)
            except Exception as e:
                logger.exception("Error stopping ffmpeg for %s: %s", self.api.username, e)
            finally:
                self.proc = None
                self._running = False
            return True

    def is_running(self):
        with self._lock:
            if not self._running or self.proc is None:
                return False
            return self.proc.poll() is None
