import requests

def is_user_live(username):
    """Check if the TikTok user is live (simplified check)."""
    try:
        url = f"https://www.tiktok.com/@{username}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        # Look for the live badge in HTML
        return 'LIVE' in resp.text.upper()
    except Exception as e:
        print(f"[ERROR] Failed to check live status for {username}: {e}")
        return False
