# src/core/tiktok_api.py
import subprocess
import logging
import shutil

logger = logging.getLogger("TikTokAPI")

class TikTokAPI:
    def __init__(self, username):
        self.username = username
        # Detect yt-dlp path
        self.yt_dlp_path = shutil.which("yt-dlp")
        if not self.yt_dlp_path:
            logger.error("yt-dlp not found in PATH. Install it or check your environment.")

    def is_live(self):
        if not self.yt_dlp_path:
            return False
        cmd = [self.yt_dlp_path, f"https://www.tiktok.com/@{self.username}", "--dump-json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            output = proc.stdout
            if '"is_live":true' in output:
                return True
            return False
        except Exception as e:
            logger.error("Failed to check live status for %s: %s", self.username, e)
            return False
