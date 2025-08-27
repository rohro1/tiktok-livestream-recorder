import os

def get_or_create_user_folder(username):
    base_folder = os.path.join("drive", username)
    os.makedirs(base_folder, exist_ok=True)
    return base_folder
