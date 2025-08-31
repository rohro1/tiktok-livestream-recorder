# src/core/tiktok_api.py
import subprocess
import json
import logging
import shlex
import re
import requests
from typing import Tuple

logger = logging.getLogger("tiktok_api")

class TikTokAPI:
    def __init__(self, username: str):
        self.username = username
        self.page_url = f"https://www.tiktok.com/@{username}"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _run_ytdlp_json(self, url: str):
        cmd = ["yt-dlp", "-j", url]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if p.returncode != 0:
                logger.debug("yt-dlp returned non-zero: %s", p.stderr.strip())
                return None
            return json.loads(p.stdout)
        except Exception:
            logger.exception("yt-dlp probe failed")
            return None

    def _check_profile_html_for_live(self) -> Tuple[bool, str]:
        """
        Fetch profile HTML and try to find JSON that indicates live status.
        Returns (is_live, possible_stream_url_or_none)
        """
        try:
            r = requests.get(self.page_url, headers=self.headers, timeout=10)
            text = r.text
            # look for simple flags
            if re.search(r'\b"isLive"\s*:\s*true', text) or re.search(r'\b"live"\s*:\s*true', text, re.I):
                # can't guarantee stream url, but report live
                return True, None
            # also search for https://...m3u8 occurrences
            m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', text)
            if m:
                return True, m.group(1)
        except Exception:
            logger.exception("HTML check failed")
        return False, None

    def is_live_and_get_stream_url(self) -> Tuple[bool, str]:
        """
        Multi-step approach:
         1. Try yt-dlp JSON extraction for the profile — this often contains "is_live" and formats with m3u8.
         2. If that fails, GET profile HTML and search for indicators (isLive, m3u8 URLs).
         3. As a last resort, check the @user/live URL or return (True, None) when heuristics indicate live.
        """
        # 1) yt-dlp probe
        info = self._run_ytdlp_json(self.page_url)
        if info:
            is_live = bool(info.get("is_live") or info.get("live") or info.get("live_status") == "live")
            formats = info.get("formats") or []
            # prefer m3u8/hls
            for f in sorted(formats, key=lambda x: x.get("height") or 0, reverse=True):
                proto = f.get("protocol", "") or ""
                ext = (f.get("ext") or "").lower()
                if "m3u8" in proto or ext == "m3u8" or "hls" in proto:
                    return True, f.get("url")
            # top-level url
            if is_live and info.get("url"):
                return True, info.get("url")
            if is_live:
                return True, None

        # 2) HTML heuristics
        is_live_html, url_html = self._check_profile_html_for_live()
        if is_live_html:
            return True, url_html

        # 3) check /live endpoint quickly (may redirect)
        try:
            r = requests.head(f"{self.page_url}/live", timeout=8, allow_redirects=True)
            if r.status_code in (200, 302) and "location" in r.headers:
                # redirect may point to live page
                return True, None
            if r.status_code == 200:
                # might show live page
                return True, None
        except Exception:
            pass

        # Try direct API
        try:
            api_url = f"https://www.tiktok.com/api/live/detail/?aid=1988&uniqueId={self.username}"
            response = requests.get(api_url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                room_info = data.get('LiveRoomInfo', {})
                if room_info.get('status') == 2:  # 2 means live
                    return True, f"https://www.tiktok.com/@{self.username}/live"
        except:
            pass

        return False, None

    def get_user_info(self, username):
        """Get user profile info"""
        try:
            url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}"
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error getting user info for {username}: {e}")
            return None
