import subprocess
import logging

logger = logging.getLogger("tiktok-api")

class TikTokAPI:
    def __init__(self, username: str):
        self.username = username.strip("@")

    def get_live_url(self):
        """
        Returns m3u8 live stream URL if user is live, else None.
        Uses yt-dlp.
        """
        url = f"https://www.tiktok.com/@{self.username}/live"
        try:
            result = subprocess.run(
                ["yt-dlp", "-g", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                live_url = result.stdout.strip().splitlines()[0]
                logger.info("Live URL fetched for %s: %s", self.username, live_url)
                return live_url
            else:
                logger.debug("No live stream found for %s", self.username)
                return None
        except Exception as e:
            logger.error("yt-dlp failed for %s: %s", self.username, e)
            return None

    def is_live(self):
        return self.get_live_url() is not None
