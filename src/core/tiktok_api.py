# tiktok_api.py
import requests
import json
import time

class TikTokAPI:
    """
    Minimal TikTok livestream API wrapper
    """
    def __init__(self, username):
        self.username = username
        self.live_id = None
        self.is_live_status = False

    def update_live_status(self):
        """
        Fetch current live status from TikTok's unofficial API
        """
        try:
            url = f"https://www.tiktok.com/@{self.username}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                self.is_live_status = False
                return

            html = resp.text
            # Search for livestream info
            if '"is_live":true' in html:
                self.is_live_status = True
            else:
                self.is_live_status = False
        except Exception as e:
            print(f"[TikTokAPI] Error checking live status for {self.username}: {e}")
            self.is_live_status = False

    def is_live(self):
        self.update_live_status()
        return self.is_live_status

    def get_stream_url(self):
        """
        Get actual livestream URL for ffmpeg recording
        """
        if not self.is_live():
            return None
        # Use TikTok's unofficial API / livestream endpoint
        try:
            api_url = f"https://m.tiktok.com/api/live/detail/?username={self.username}"
            headers = {
                "User-Agent": "Mozilla/5.0"
            }
            resp = requests.get(api_url, headers=headers, timeout=10)
            data = resp.json()
            stream_url = data.get("data", {}).get("stream_url", None)
            if stream_url:
                return stream_url
            else:
                # fallback dummy, or raise
                return None
        except Exception as e:
            print(f"[TikTokAPI] Error fetching stream URL for {self.username}: {e}")
            return None
