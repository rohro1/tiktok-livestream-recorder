# src/core/tiktok_api.py
import subprocess
import json
import logging

logger = logging.getLogger("TikTokAPI")
logger.setLevel(logging.INFO)

class TikTokAPI:
    """
    Minimal wrapper to check if a TikTok user is live using yt-dlp.
    """
    def __init__(self, username):
        self.username = username
        self.stream_url = None

    def is_live(self):
        """
        Returns True if the user is currently live.
        """
        try:
            # yt-dlp command to get live info
            cmd = [
                "yt-dlp",
                f"https://www.tiktok.com/@{self.username}",
                "--dump-json",
                "--skip-download"
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                logger.warning("yt-dlp failed for %s: %s", self.username, proc.stderr)
                return False
            data = json.loads(proc.stdout)
            is_live = data.get("is_live", False)
            if is_live:
                self.stream_url = data.get("url")
            else:
                self.stream_url = None
            return is_live
        except Exception:
            logger.exception("Failed to check live status for %s", self.username)
            self.stream_url = None
            return False

    def get_stream_url(self):
        return self.stream_url
