# src/utils/google_drive_uploader.py
import os
import logging
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("drive_uploader")

class GoogleDriveUploader:
    def __init__(self, drive_service, drive_folder_root="TikTokRecordings"):
        self.service = drive_service
        self.root_name = drive_folder_root
        self.root_id = self._ensure_folder(self.root_name)

    def _ensure_folder(self, folder_name, parent_id=None):
        q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = self.service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        file = self.service.files().create(body=metadata, fields="id").execute()
        return file.get("id")

    def upload_file(self, local_path, remote_subfolder=None):
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)
        folder_id = self.root_id
        if remote_subfolder:
            # remote_subfolder can be "username/YYYY-MM-DD" — create nested folders
            parts = str(remote_subfolder).strip("/").split("/")
            parent = self.root_id
            for p in parts:
                parent = self._ensure_folder(p, parent_id=parent)
            folder_id = parent
        file_metadata = {"name": os.path.basename(local_path), "parents": [folder_id]}
        media = MediaFileUpload(local_path, resumable=True)
        request = self.service.files().create(body=file_metadata, media_body=media, fields="id")
        result = request.execute()
        logger.info("Uploaded %s -> drive id=%s", local_path, result.get("id"))
        return result.get("id")
