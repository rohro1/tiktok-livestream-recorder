# src/utils/google_drive_uploader.py
import os
from datetime import datetime
from typing import Optional
from googleapiclient.http import MediaFileUpload
from src.utils.oauth_drive import get_drive_service

def _get_or_create_folder(service, name, parent_id=None):
    """Return folder id for folder with given name (create if missing)."""
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    resp = service.files().list(q=query, fields="files(id, name)").execute()
    items = resp.get("files", [])
    if items:
        return items[0]["id"]

    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]

def upload_file_to_drive(username: str, file_path: str, mime_type: Optional[str] = None) -> dict:
    """
    Uploads a file to Drive under TikTokRecordings/username/YYYY-MM-DD/.
    Returns created file resource dict.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    service = get_drive_service()  # build/refreshes credentials here

    date_folder = datetime.now().strftime("%Y-%m-%d")
    root_folder = "TikTokRecordings"

    root_id = _get_or_create_folder(service, root_folder, None)
    user_id = _get_or_create_folder(service, username, root_id)
    date_id = _get_or_create_folder(service, date_folder, user_id)

    metadata = {"name": os.path.basename(file_path), "parents": [date_id]}
    media = MediaFileUpload(file_path, mimetype=mime_type or "video/mp4", resumable=True)

    created = service.files().create(body=metadata, media_body=media, fields="id,name").execute()
    print(f"✅ Uploaded {file_path} to {root_folder}/{username}/{date_folder}")
    return created
