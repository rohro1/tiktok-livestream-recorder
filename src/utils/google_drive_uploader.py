import os
from googleapiclient.http import MediaFileUpload

class GoogleDriveUploader:
    def __init__(self, service, drive_folder_root="TikTokRecordings"):
        self.service = service
        self.root = drive_folder_root
        self._ensure_root_folder()

    def _ensure_root_folder(self):
        folders = self.service.files().list(q=f"name='{self.root}' and mimeType='application/vnd.google-apps.folder'",
                                            spaces='drive').execute()
        if folders["files"]:
            self.root_id = folders["files"][0]["id"]
        else:
            file_metadata = {"name": self.root, "mimeType": "application/vnd.google-apps.folder"}
            folder = self.service.files().create(body=file_metadata, fields="id").execute()
            self.root_id = folder["id"]

    def upload_file(self, local_path, remote_subfolder=None):
        folder_id = self.root_id
        if remote_subfolder:
            # Check if subfolder exists
            q = f"name='{remote_subfolder}' and mimeType='application/vnd.google-apps.folder' and '{self.root_id}' in parents"
            folders = self.service.files().list(q=q, spaces='drive').execute()
            if folders["files"]:
                folder_id = folders["files"][0]["id"]
            else:
                file_metadata = {"name": remote_subfolder, "mimeType": "application/vnd.google-apps.folder", "parents":[self.root_id]}
                folder = self.service.files().create(body=file_metadata, fields="id").execute()
                folder_id = folder["id"]
        file_metadata = {"name": os.path.basename(local_path), "parents":[folder_id]}
        media = MediaFileUpload(local_path, resumable=True)
        self.service.files().create(body=file_metadata, media_body=media, fields="id").execute()
