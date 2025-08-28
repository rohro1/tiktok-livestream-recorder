import os

def ensure_user_folder(username, date_str):
    path = os.path.join("recordings", username, date_str)
    os.makedirs(path, exist_ok=True)
    return path
