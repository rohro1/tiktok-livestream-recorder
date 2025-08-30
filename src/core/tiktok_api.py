# src/core/tiktok_api.py
import subprocess
import json
import logging
import shlex
import re
from shutil import which

logger = logging.getLogger("tiktok_api")

# This uses yt-dlp to probe TikTok and extract a live stream URL.
# It attempts to extract HLS or dash manifest URL for live recording.

class TikTokAPI:
    def __init__(self, username: str):
        self.username = username
        self.page_url = f"https://www.tiktok.com/@{username}"

    def _run_ytdlp_json(self, url):
        # ensure yt-dlp in path provided by requirements
        cmd = f"yt-dlp -j {shlex.quote(url)}"
        try:
            p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=20)
            if p.returncode != 0:
                logger.debug("yt-dlp failed: %s", p.stderr.strip())
                return None
            return json.loads(p.stdout)
        except Exception as e:
            logger.exception("yt-dlp json fetch failed: %s", e)
            return None

    def is_live_and_get_stream_url(self):
        """
        Returns (is_live: bool, stream_url or None).
        Strategy:
         - use yt-dlp JSON extraction (yt-dlp often returns 'is_live' and/or formats with protocol m3u8)
         - otherwise attempt to parse webpage for 'is_live' signals (simple fallback)
        """
        info = self._run_ytdlp_json(self.page_url)
        if info:
            # yt-dlp often has 'is_live' or formats with 'protocol' == 'm3u8' / 'dash'
            is_live = info.get("is_live") or info.get("live", False)
            # find best m3u8
            formats = info.get("formats") or []
            # choose format with ext m3u8 or protocol m3u8_native/https_dash? pick first live-like
            for f in sorted(formats, key=lambda x: x.get("height") or 0):
                proto = f.get("protocol", "") or ""
                ext = f.get("ext", "") or ""
                if "m3u8" in proto or ext == "m3u8" or "hls" in proto:
                    return True, f.get("url")
            # sometimes yt-dlp returns 'url' top-level for live
            url = info.get("url")
            if is_live and url:
                return True, url
            return bool(is_live), None

        # fallback: try to detect 'live' via web page snippet (cheap heuristic)
        try:
            import requests
            r = requests.get(self.page_url, timeout=12)
            text = r.text.lower()
            if "is live" in text or "watch live" in text or "live with" in text:
                # we still need a stream url but return True to attempt to fetch again
                return True, None
        except Exception:
            pass
        return False, None
