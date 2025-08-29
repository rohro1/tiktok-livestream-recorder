"""
src/core/tiktok_api.py

Provides a thin wrapper around yt-dlp to:
 - determine whether a TikTok username is currently live
 - resolve a direct stream URL (m3u8 or other) for recording

Usage:
    api = TikTokAPI("username_here")
    if api.is_live():
        url = api.get_stream_url()
"""

from dataclasses import dataclass
import subprocess
import json
import shlex
import logging
import time

logger = logging.getLogger("tiktok-api")
logger.setLevel(logging.INFO)

YT_DLP_CMD = "yt-dlp"  # ensure this command is installed/available in PATH

@dataclass
class TikTokAPI:
    username: str
    base_page: str = None

    def __post_init__(self):
        # TikTok user live page url
        # TikTok uses regionised domains; the standard public profile is this form:
        self.base_page = f"https://www.tiktok.com/@{self.username}"

    def _run_yt_dlp_json(self, extra_args=None, timeout=30):
        """
        Run yt-dlp to get JSON metadata. Returns parsed JSON dict or None.
        """
        extra_args = extra_args or []
        cmd = [YT_DLP_CMD, "--no-warnings", "--print-json", "--skip-download"] + extra_args + [self.base_page]
        try:
            logger.debug("Running yt-dlp: %s", " ".join(shlex.quote(p) for p in cmd))
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if proc.returncode != 0:
                logger.debug("yt-dlp exit %s stdout=%s stderr=%s", proc.returncode, proc.stdout, proc.stderr)
                return None
            # yt-dlp may return multiple JSON objects; take the last non-empty line
            out = proc.stdout.strip().splitlines()
            if not out:
                return None
            raw = out[-1].strip()
            return json.loads(raw)
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp timed out when probing %s", self.base_page)
            return None
        except Exception as e:
            logger.exception("yt-dlp failed: %s", e)
            return None

    def is_live(self):
        """
        Try to detect whether the user is live. Strategy:
        - ask yt-dlp for JSON metadata and check for stream info or 'is_live' indicators.
        - return True if a live stream url can be located.
        """
        meta = self._run_yt_dlp_json(extra_args=["--no-check-certificate"])
        if not meta:
            return False

        # yt-dlp sets "is_live" or it may expose 'formats' with 'protocol'='m3u8_native' etc.
        if meta.get("is_live") is True:
            return True

        # inspect formats for m3u8 or live protocol
        formats = meta.get("formats") or []
        for fmt in formats:
            proto = fmt.get("protocol", "")
            # m3u8_native, m3u8_dash, or 'http_dash_segments' etc. consider these live
            if "m3u8" in proto or fmt.get("ext") == "m3u8":
                return True

        # fallback: if description contains "LIVE" or extractor_note
        extractor_note = meta.get("extractor_notes", "") or meta.get("uploader", "")
        if extractor_note and "live" in extractor_note.lower():
            return True

        return False

    def get_stream_url(self, prefer="best"):
        """
        Resolve the direct stream URL suitable for feeding into ffmpeg.
        Uses `yt-dlp -g` to print direct URLs; returns the first matching HLS or best variant.
        Returns None if not resolvable.
        """
        try:
            # yt-dlp -g returns direct URLs (one-per-line). Use --no-check-certificate to reduce failures.
            cmd = [YT_DLP_CMD, "-g", "--no-check-certificate", self.base_page]
            logger.debug("Running yt-dlp to get stream URL: %s", " ".join(cmd))
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if proc.returncode != 0:
                logger.debug("yt-dlp -g failed: stdout=%s stderr=%s", proc.stdout, proc.stderr)
                return None
            lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
            if not lines:
                return None

            # prefer HLS (m3u8) urls if present
            for l in lines:
                if ".m3u8" in l:
                    return l

            # otherwise return the first url
            return lines[0]
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp -g timed out for %s", self.base_page)
            return None
        except Exception as e:
            logger.exception("Error resolving stream url for %s: %s", self.username, e)
            return None
