import os

def make_user_folders(username: str, base_dir: str = "recordings") -> str:
    """
    Creates a folder structure for a TikTok username if it doesn't already exist.
    Returns the path to the user's folder.
    """
    # recordings/<username>
    user_folder = os.path.join(base_dir, username)
    os.makedirs(user_folder, exist_ok=True)

    # recordings/<username>/raw
    raw_folder = os.path.join(user_folder, "raw")
    os.makedirs(raw_folder, exist_ok=True)

    # recordings/<username>/processed
    processed_folder = os.path.join(user_folder, "processed")
    os.makedirs(processed_folder, exist_ok=True)

    return user_folder
