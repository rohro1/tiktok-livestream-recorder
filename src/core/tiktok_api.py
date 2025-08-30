import yt_dlp
import logging

logger = logging.getLogger("tiktok-api")

class TikTokAPI:
    """
    Wrapper around yt-dlp to check if a TikTok user is live and get the livestream URL.
    """
    def __init__(self, username: str):
        self.username = username
        self.url = f"https://www.tiktok.com/@{username}/live"

    def is_live(self) -> bool:
        """
        Check if the user is live by trying to extract a playable livestream URL.
        Returns True if a stream URL is found, False otherwise.
        """
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info and info.get("is_live"):
                    return True
        except Exception as e:
            logger.debug(f"{self.username} not live or fetch failed: {e}")
        return False

    def get_stream_url(self) -> str | None:
        """
        Returns the actual livestream URL (m3u8) if available.
        """
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info and info.get("is_live"):
                    formats = info.get("formats") or []
                    # Pick lowest resolution ≥ 480p if available
                    for f in formats:
                        if "m3u8" in f.get("protocol", ""):
                            return f.get("url")
        except Exception as e:
            logger.debug(f"Could not fetch stream URL for {self.username}: {e}")
        return None
