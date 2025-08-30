# src/core/tiktok_api.py
import subprocess
import json
import logging

logger = logging.getLogger("TikTokAPI")
logger.setLevel(logging.INFO)

class TikTokAPI:
    def __init__(self, username, timeout=15):
        self.username = username
        self.timeout = timeout  # seconds

    def is_live(self):
        """
        Returns True if user is currently live, False otherwise.
        Handles empty output, JSON errors, and timeouts gracefully.
        """
        try:
            # yt-dlp JSON query for livestream
            cmd = [
                "yt-dlp",
                f"https://www.tiktok.com/@{self.username}",
                "--dump-json",
                "--skip-download"
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            output = result.stdout.strip()
            if not output:
                logger.warning("TikTokAPI: empty stdout for %s", self.username)
                return False
            data = json.loads(output)
            is_live = data.get("is_live", False)
            return bool(is_live)
        except subprocess.TimeoutExpired:
            logger.error("TikTokAPI: Command timed out for %s", self.username)
            return False
        except json.JSONDecodeError as e:
            logger.error("TikTokAPI: JSON decode error for %s: %s", self.username, e)
            return False
        except Exception as e:
            logger.exception("TikTokAPI: Unexpected error for %s: %s", self.username, e)
            return False
