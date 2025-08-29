# src/utils/folder_manager.py

from googleapiclient.errors import HttpError
from .oauth_drive import get_drive_service, load_credentials
from datetime import datetime
import os

def create_folders_for_users(usernames):
    """
    Creates a folder for each TikTok username and a subfolder for today's date.
    Returns a dict mapping username -> folder_id
    """
    creds = load_credentials()
    service = get_drive_service(creds)
    folder_ids = {}

    for username in usernames:
        # 1. Check if main user folder exists
        query = f"name='{username}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if files:
            user_folder_id = files[0]['id']
        else:
            file_metadata = {
                'name': username,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            user_folder = service.files().create(body=file_metadata, fields='id').execute()
            user_folder_id = user_folder['id']

        # 2. Create subfolder for today
        today = datetime.now().strftime("%m-%d-%Y")
        query = f"name='{today}' and '{user_folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if files:
            date_folder_id = files[0]['id']
        else:
            file_metadata = {
                'name': today,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [user_folder_id]
            }
            date_folder = service.files().create(body=file_metadata, fields='id').execute()
            date_folder_id = date_folder['id']

        folder_ids[username] = date_folder_id

    return folder_ids
