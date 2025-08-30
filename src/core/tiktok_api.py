import subprocess
import logging

logger = logging.getLogger("tiktok-api")

class TikTokAPI:
    def __init__(self, username: str):
        self.username = username

    def get_stream_url(self):
        """Return HLS URL if user is live, else None"""
        try:
            cmd = [
                "yt-dlp",
                f"https://www.tiktok.com/@{self.username}/live",
                "--no-warnings",
                "--skip-download",
                "-g"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.warning("yt-dlp error for %s: %s", self.username, e)
        return None

    def is_live(self):
        return self.get_stream_url() is not None
