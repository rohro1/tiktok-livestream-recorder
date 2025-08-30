import subprocess

class TikTokAPI:
    def __init__(self, username):
        self.username = username.strip("@")

    def is_live(self):
        """Return (is_live: bool, stream_url: str|None)"""
        url = f"https://www.tiktok.com/@{self.username}/live"
        try:
            result = subprocess.run(
                ["yt-dlp", "-g", url],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                return True, result.stdout.strip().splitlines()[0]
            return False, None
        except Exception:
            return False, None
