# src/core/tiktok_api.py
import subprocess
import json
import logging

logger = logging.getLogger("TikTokAPI")

class TikTokAPI:
    def __init__(self, username):
        self.username = username
        self.url = f"https://www.tiktok.com/@{username}"
        # path to yt-dlp; adjust if needed
        import shutil
        self.yt_dlp_cmd = shutil.which("yt-dlp") or "yt-dlp"

    def is_live(self):
        try:
            # Increase timeout to 30s to avoid frequent timeouts
            result = subprocess.run(
                [self.yt_dlp_cmd, self.url, "--dump-json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            data = json.loads(result.stdout)
            # 'is_live' key may exist; check for live status
            live = data.get("is_live") or False
            return live
        except subprocess.TimeoutExpired:
            logger.error("Failed to check live status for %s: Command timed out", self.username)
            return False
        except Exception as e:
            logger.exception("Failed to check live status for %s: %s", self.username, e)
            return False
