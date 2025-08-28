import os
from src.utils.google_drive_uploader import DriveUploader

# === CONFIG ===
TEST_FILE = "sample.mp4"  # make sure this file exists in project root
TEST_USERNAMES = ["peatown_973", "justdoyoubro"]  # test usernames

# Ensure test file exists
if not os.path.exists(TEST_FILE):
    with open(TEST_FILE, "w") as f:
        f.write("Hello TikTok Drive!")  # dummy content

def main():
    uploader = DriveUploader()

    for username in TEST_USERNAMES:
        print(f"\n📤 Uploading test file for {username}")
        uploader.upload_file(username, TEST_FILE)

if __name__ == "__main__":
    main()
