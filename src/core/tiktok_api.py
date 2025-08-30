import yt_dlp
import logging

logger = logging.getLogger("tiktok-api")

class TikTokAPI:
    def __init__(self, username: str):
        self.username = username
        self.url = f"https://www.tiktok.com/@{username}/live"

    def is_live(self) -> bool:
        """
        Uses yt-dlp to check if the TikTok user is live.
        If yt-dlp finds a streaming URL, the user is live.
        """
        try:
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info and info.get("is_live"):
                    return True
        except Exception as e:
            logger.debug("yt-dlp check failed for %s: %s", self.username, e)
        return False

    def get_stream_url(self) -> str | None:
        """
        Returns the m3u8 livestream URL if live, otherwise None.
        """
        try:
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info and info.get("is_live") and "url" in info:
                    return info["url"]
        except Exception as e:
            logger.debug("yt-dlp stream fetch failed for %s: %s", self.username, e)
        return None
