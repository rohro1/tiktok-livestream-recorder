# src/utils/folder_manager.py
import os

def make_user_folders(usernames, base_dir):
    """Ensure each username has its own folder under base_dir."""
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    for username in usernames:
        user_folder = os.path.join(base_dir, username)  # <-- FIX: use username not list
        os.makedirs(user_folder, exist_ok=True)
