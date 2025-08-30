# src/core/tiktok_api.py
import logging
import requests

logger = logging.getLogger("tiktok_api")
logger.setLevel(logging.INFO)

class TikTokAPI:
    """
    Handles checking if a TikTok username is live and getting the stream URL.
    """

    def __init__(self, username):
        self.username = username
        self.user_id = None
        self.live_url = None

    def get_user_info(self):
        """
        Fetch user info from TikTok API to get user_id
        """
        try:
            resp = requests.get(f"https://www.tiktok.com/@{self.username}", timeout=10)
            if resp.status_code == 200:
                # TikTok returns HTML; parse userId from initial state
                import re, json
                match = re.search(r'window\.__INIT_PROPS__\s*=\s*({.*?});', resp.text)
                if match:
                    data = json.loads(match.group(1))
                    self.user_id = data.get("userData", {}).get("user", {}).get("id")
            return self.user_id
        except Exception:
            logger.debug(f"Failed to fetch user info for {self.username}", exc_info=True)
            return None

    def is_live(self):
        """
        Returns True if user is live, False otherwise
        """
        try:
            from yt_dlp.utils import DownloadError
            import yt_dlp
            url = f"https://www.tiktok.com/@{self.username}"
            ydl_opts = {"quiet": True, "skip_download": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                live_status = info.get("is_live") or False
                if live_status:
                    self.live_url = info.get("url")
                    return True
                else:
                    self.live_url = None
                    return False
        except Exception:
            self.live_url = None
            return False

    def get_live_url(self):
        """
        Returns live stream URL or None
        """
        return self.live_url
