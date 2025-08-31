# src/utils/folder_manager.py
import os

def make_user_folders(usernames, recordings_dir):
    for u in usernames:
        os.makedirs(os.path.join(recordings_dir, u), exist_ok=True)
