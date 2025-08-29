# TikTokLiveRecorder/src/core/tiktok_api.py
import requests
import json

class TikTokAPI:
    def __init__(self, username):
        self.username = username
        self.user_id = self.get_user_id(username)
        self.live_url = None

    def get_user_id(self, username):
        """Get TikTok user ID from username"""
        try:
            url = f"https://www.tiktok.com/@{username}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                return None
            text = r.text
            start = text.find('{"id":"')
            if start == -1:
                return None
            start += len('{"id":"')
            end = text.find('"', start)
            return text[start:end]
        except Exception as e:
            print(f"Error getting user ID for {username}: {e}")
            return None

    def is_live(self):
        """Check if the user is live and get the live URL"""
        if not self.user_id:
            return False
        try:
            url = f"https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/live/room?user_id={self.user_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            data = r.json()
            if data.get("data") and data["data"].get("status") == 2:
                self.live_url = data["data"]["stream_url"]["hls_pull_url"]
                return True
            return False
        except Exception as e:
            return False

    def get_live_url(self):
        return self.live_url
