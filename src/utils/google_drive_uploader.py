# src/utils/google_drive_uploader.py
import os
import logging
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("google-drive-uploader")
logger.setLevel(logging.INFO)

class GoogleDriveUploader:
    def __init__(self, drive_service, drive_folder_root="TikTokRecordings"):
        self.drive_service = drive_service
        self.drive_folder_root = drive_folder_root
        self.root_folder_id = self._ensure_folder(self.drive_folder_root)

    def _ensure_folder(self, folder_name, parent_id=None):
        """
        Ensure that a folder exists on Google Drive, create it if not.
        """
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        response = self.drive_service.files().list(q=query, fields="files(id,name)").execute()
        files = response.get("files", [])
        if files:
            return files[0]["id"]

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = self.drive_service.files().create(body=metadata, fields="id").execute()
        return folder["id"]

    def upload_file(self, file_path, remote_subfolder=None):
        """
        Upload a file to Google Drive under a subfolder.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        parent_folder_id = self.root_folder_id
        if remote_subfolder:
            parent_folder_id = self._ensure_folder(remote_subfolder, self.root_folder_id)

        media = MediaFileUpload(file_path, resumable=True)
        metadata = {"name": os.path.basename(file_path), "parents": [parent_folder_id]}
        file = self.drive_service.files().create(body=metadata, media_body=media, fields="id").execute()
        logger.info(f"Uploaded {file_path} to Google Drive with file ID: {file['id']}")
        return file["id"]
