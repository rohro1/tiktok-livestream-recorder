import random

class TikTokAPI:
    def is_live(self, username):
        print(f"[*] Checking if {username} is live...")
        return random.choice([True, False, False])