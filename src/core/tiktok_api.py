# src/core/tiktok_api.py
import yt_dlp
import logging

logger = logging.getLogger("tiktok-api")
logger.setLevel(logging.INFO)

class TikTokAPI:
    def __init__(self, username):
        self.username = username
        self.url = f"https://www.tiktok.com/@{username}/live"

    def is_live(self):
        """
        Checks if the user is live using yt-dlp's URL extraction.
        Returns True if live, False if offline.
        """
        ydl_opts = {
            "quiet": True,
            "simulate": True,  # We don't want to download the stream, just simulate
            "extract_flat": True,  # Extract the URL without downloading
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.url, download=False)
                if "entries" in info:
                    live_entry = next((entry for entry in info["entries"] if entry.get("is_live")), None)
                    return live_entry is not None
            except Exception as e:
                logger.error(f"Error checking live status for {self.username}: {e}")
        return False

    def get_live_url(self):
        """
        Returns the URL of the livestream if live, otherwise None.
        """
        ydl_opts = {
            "quiet": True,
            "simulate": True,
            "extract_flat": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.url, download=False)
                if "entries" in info:
                    live_entry = next((entry for entry in info["entries"] if entry.get("is_live")), None)
                    if live_entry:
                        return live_entry.get("url")
            except Exception as e:
                logger.error(f"Error fetching live stream URL for {self.username}: {e}")
        return None
