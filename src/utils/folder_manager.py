# src/utils/folder_manager.py
from src.utils.oauth_drive import get_drive_service
from googleapiclient.errors import HttpError

def create_folders_for_users(usernames):
    """
    Creates a folder for each username if it doesn't exist already.
    Returns dict of username -> folder_id
    """
    service = get_drive_service()
    if service is None:
        raise Exception("Google Drive service not authorized.")
    
    folder_ids = {}
    for username in usernames:
        query = f"name='{username}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        try:
            result = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = result.get("files", [])
            if files:
                folder_ids[username] = files[0]["id"]
            else:
                file_metadata = {
                    "name": username,
                    "mimeType": "application/vnd.google-apps.folder"
                }
                file = service.files().create(body=file_metadata, fields="id").execute()
                folder_ids[username] = file.get("id")
        except HttpError as e:
            print(f"Error creating folder for {username}: {e}")
    return folder_ids
