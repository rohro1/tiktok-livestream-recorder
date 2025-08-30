import os

def make_user_folders(usernames, base_dir):
    for u in usernames:
        os.makedirs(os.path.join(base_dir, u), exist_ok=True)
