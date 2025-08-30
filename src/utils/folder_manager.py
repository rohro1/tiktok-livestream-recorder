# src/utils/folder_manager.py
import os

def make_user_folders(usernames, recordings_dir):
    # keep minimal: local folders are not required (we use /tmp), but keep for compatibility
    for u in usernames:
        os.makedirs(os.path.join(recordings_dir, u), exist_ok=True)
