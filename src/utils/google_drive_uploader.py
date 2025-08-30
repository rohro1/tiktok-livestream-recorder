# src/utils/google_drive_uploader.py
import os
import logging
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("gdrive-uploader")
logger.setLevel(logging.INFO)

class GoogleDriveUploader:
    def __init__(self, drive_service, drive_folder_root="TikTokRecordings"):
        self.drive = drive_service
        self.root_name = drive_folder_root
        self.root_id = self._ensure_folder(self.root_name)
        logger.info("Drive root folder id=%s", self.root_id)

    def _ensure_folder(self, folder_name, parent_id=None):
        q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        resp = self.drive.files().list(q=q, fields="files(id,name)").execute()
        files = resp.get("files", [])
        if files:
            return files[0]["id"]
        # create folder
        metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        f = self.drive.files().create(body=metadata, fields="id").execute()
        logger.info("Created folder %s id=%s", folder_name, f.get("id"))
        return f.get("id")

    def upload_file(self, local_path, remote_subfolder=None):
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)
        parent_id = self.root_id
        if remote_subfolder:
            parent_id = self._ensure_folder(remote_subfolder, parent_id=self.root_id)
        media = MediaFileUpload(local_path, resumable=True)
        metadata = {"name": os.path.basename(local_path), "parents": [parent_id]}
        f = self.drive.files().create(body=metadata, media_body=media, fields="id").execute()
        logger.info("Uploaded %s to Drive id=%s", local_path, f.get("id"))
        return f.get("id")
