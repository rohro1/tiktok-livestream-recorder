# src/core/tiktok_api.py
import logging
import shlex
import subprocess
import json
from typing import Tuple, Optional
import requests

logger = logging.getLogger("tiktok_api")

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"

class TikTokAPI:
    """
    Multi-strategy TikTok "is live" + stream URL finder:
      1) Use yt-dlp JSON extraction (best for getting stream URL).
      2) Probe the mobile web page with a mobile UA to heuristically find "live" indicators.
      3) Return a boolean and (if found) stream URL.
    """
    def __init__(self, username: str):
        self.username = username
        self.page_url = f"https://www.tiktok.com/@{username}"

    def _yt_dlp_json(self, url: str) -> Optional[dict]:
        try:
            cmd = f"yt-dlp -j {shlex.quote(url)}"
            p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=20)
            if p.returncode != 0 or not p.stdout:
                logger.debug("yt-dlp returned no JSON or nonzero exit for %s: %s", url, p.stderr.strip())
                return None
            return json.loads(p.stdout)
        except Exception:
            logger.exception("yt-dlp JSON extraction failed")
            return None

    def _probe_mobile_page(self, url: str) -> Tuple[bool, Optional[str]]:
        try:
            headers = {"User-Agent": MOBILE_UA}
            r = requests.get(url, headers=headers, timeout=12)
            text = r.text.lower()
            # heuristics: look for 'is live', 'watch live', "LIVE" or 'is_live'
            if "is live" in text or "watch live" in text or '"isLiveBroadcast":true' in text or '"is_live":true' in text:
                # no stream url, but confirms live
                return True, None
            # some pages include 'm3u8' in markup
            if "m3u8" in text:
                # try to extract first http...m3u8 occurrences
                import re
                m = re.search(r"https?://[^\"]+\.m3u8", text)
                if m:
                    return True, m.group(0)
        except Exception:
            logger.debug("mobile probe failed for %s", url, exc_info=True)
        return False, None

    def is_live_and_get_stream_url(self) -> Tuple[bool, Optional[str]]:
        # 1) Try yt-dlp
        info = self._yt_dlp_json(self.page_url)
        if info:
            is_live = info.get("is_live") or info.get("live") or False
            # check formats
            formats = info.get("formats") or []
            # prefer m3u8 or hls formats
            best_url = None
            for f in reversed(sorted(formats, key=lambda x: x.get("height") or 0)):
                proto = (f.get("protocol") or "").lower()
                ext = (f.get("ext") or "").lower()
                if "m3u8" in proto or ext == "m3u8" or "hls" in proto:
                    best_url = f.get("url")
                    break
            if not best_url:
                best_url = info.get("url")
            if is_live:
                return True, best_url

        # 2) Mobile web probe heuristics
        try:
            is_live, url = self._probe_mobile_page(self.page_url)
            if is_live:
                return True, url
        except Exception:
            logger.exception("mobile probe exception")

        # 3) fallback: try m.tiktok or /live url
        fallback_urls = [
            f"https://m.tiktok.com/v/{self.username}",
            f"https://www.tiktok.com/@{self.username}/live",
            self.page_url
        ]
        for u in fallback_urls:
            try:
                is_live, url = self._probe_mobile_page(u)
                if is_live:
                    return True, url
            except Exception:
                pass

        return False, None
