import requests

class TikTokAPI:
    def __init__(self):
        pass

    def check_live(self, username):
        """
        Returns (is_live: bool, stream_url: str or None)
        """
        # Simplified placeholder for TikTok live check
        # Replace with actual TikTok API/live fetch logic
        # Here we'll simulate that the user is live 50% of the time
        import random
        is_live = random.choice([True, False])
        stream_url = f"https://tiktok.fake/stream/{username}" if is_live else None
        return is_live, stream_url
