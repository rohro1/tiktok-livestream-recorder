# src/core/tiktok_api.py
import logging
import requests

logger = logging.getLogger("tiktok_api")

class TikTokAPI:
    """
    Wrapper for TikTok live API.
    Provides methods to check if a user is live and get their livestream URL.
    """

    BASE_URL = "https://www.tiktok.com/api/live/detail/"

    def __init__(self, username: str):
        self.username = username

    def is_live(self) -> bool:
        """
        Check if the TikTok user is live.
        Returns True/False.
        """
        try:
            url = f"https://www.tiktok.com/@{self.username}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            r = requests.get(url, headers=headers, timeout=10)
            if "LIVE" in r.text or "liveRoomId" in r.text:
                return True
        except Exception as e:
            logger.error("Failed to check live status for %s: %s", self.username, e)
        return False

    def get_live_url(self) -> str | None:
        """
        Return the m3u8 playlist URL of the livestream (480p if available).
        """
        try:
            url = f"https://www.tiktok.com/@{self.username}/live"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            r = requests.get(url, headers=headers, timeout=10)
            if ".m3u8" in r.text:
                # crude extract of first playlist link
                start = r.text.find("https://")
                end = r.text.find(".m3u8", start)
                if start != -1 and end != -1:
                    return r.text[start:end+5]
        except Exception as e:
            logger.error("Failed to fetch live URL for %s: %s", self.username, e)
        return None
