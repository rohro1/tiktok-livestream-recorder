import subprocess
import logging

logger = logging.getLogger("tiktok-recorder")

class TikTokAPI:
    def __init__(self, username):
        self.username = username

    def is_live(self):
        """Check if TikTok user is live using yt-dlp"""
        try:
            url = f"https://www.tiktok.com/@{self.username}/live"
            cmd = ["yt-dlp", "--no-warnings", "--flat-playlist", "-j", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if result.returncode == 0 and result.stdout.strip():
                return True  # Live
            return False  # Not live
        except subprocess.TimeoutExpired:
            logger.warning("Timeout checking live for %s", self.username)
            return False
        except Exception as e:
            logger.error("yt-dlp check failed for %s: %s", self.username, e)
            return False
