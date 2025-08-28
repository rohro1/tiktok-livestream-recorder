import os
from googleapiclient.http import MediaFileUpload

def upload_file(service, local_file_path, username):
    if service is None:
        return
    date_folder = os.path.basename(os.path.dirname(local_file_path))
    folder_name = f"{username}/{date_folder}"
    # Check or create folder logic
    folder_id = ensure_folder(service, folder_name)
    media = MediaFileUpload(local_file_path, resumable=True)
    file_metadata = {"name": os.path.basename(local_file_path), "parents": [folder_id]}
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

def ensure_folder(service, folder_path):
    """Creates folder hierarchy on Google Drive if not exists, returns final folder_id"""
    parts = folder_path.split("/")
    parent_id = "root"
    for part in parts:
        # Search for existing folder
        query = f"name='{part}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents"
        res = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        if res['files']:
            parent_id = res['files'][0]['id']
        else:
            metadata = {"name": part, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
            folder = service.files().create(body=metadata, fields='id').execute()
            parent_id = folder['id']
    return parent_id
