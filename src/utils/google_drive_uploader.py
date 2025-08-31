"""
Google Drive Uploader
Handles uploading recordings to Google Drive with folder organization
"""

import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GoogleDriveUploader:
    def __init__(self, credentials):
        """
        Initialize Drive uploader with credentials
        
        Args:
            credentials: Google OAuth2 credentials object
        """
        self.credentials = credentials
        self.service = build('drive', 'v3', credentials=credentials)
        self.folder_cache = {}  # Cache folder IDs

    def create_folder(self, name, parent_id='root'):
        """
        Create a folder in Google Drive
        
        Args:
            name (str): Folder name
            parent_id (str): Parent folder ID (default: root)
        
        Returns:
            str: Folder ID if successful, None otherwise
        """
        try:
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"Created folder '{name}' with ID: {folder_id}")
            return folder_id
            
        except HttpError as e:
            logger.error(f"Error creating folder '{name}': {e}")
            return None

    def find_or_create_folder(self, name, parent_id='root'):
        """
        Find existing folder or create new one
        
        Args:
            name (str): Folder name
            parent_id (str): Parent folder ID
        
        Returns:
            str: Folder ID
        """
        cache_key = f"{parent_id}:{name}"
        
        # Check cache first
        if cache_key in self.folder_cache:
            return self.folder_cache[cache_key]
        
        try:
            # Search for existing folder
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
            
            results = self.service.files().list(
                q=query,
                fields='files(id, name)'
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                logger.info(f"Found existing folder '{name}': {folder_id}")
            else:
                folder_id = self.create_folder(name, parent_id)
            
            # Cache the result
            if folder_id:
                self.folder_cache[cache_key] = folder_id
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Error finding/creating folder '{name}': {e}")
            return None

    def get_folder_structure(self, username):
        """
        Get or create folder structure for a user
        Structure: TikTok Recordings / username / YYYY-MM
        
        Args:
            username (str): TikTok username
        
        Returns:
            str: Target folder ID for uploads
        """
        try:
            # Main folder
            main_folder_id = self.find_or_create_folder('TikTok Recordings')
            if not main_folder_id:
                return None
            
            # User folder
            user_folder_id = self.find_or_create_folder(username, main_folder_id)
            if not user_folder_id:
                return None
            
            # Date folder (YYYY-MM)
            date_folder = datetime.now().strftime('%Y-%m')
            date_folder_id = self.find_or_create_folder(date_folder, user_folder_id)
            
            return date_folder_id
            
        except Exception as e:
            logger.error(f"Error getting folder structure for {username}: {e}")
            return None

    def upload_video(self, file_path, username):
        """
        Upload video file to Google Drive
        
        Args:
            file_path (str): Local file path
            username (str): TikTok username
        
        Returns:
            str: Google Drive file URL if successful, None otherwise
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None

            # Get target folder
            folder_id = self.get_folder_structure(username)
            if not folder_id:
                logger.error(f"Could not create folder structure for {username}")
                return None

            # Prepare file metadata
            file_name = os.path.basename(file_path)
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }

            # Upload file
            media = MediaFileUpload(
                file_path,
                mimetype='video/mp4',
                resumable=True
            )

            logger.info(f"Uploading {file_name} to Google Drive...")
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()

            file_id = file.get('id')
            file_url = file.get('webViewLink')
            
            logger.info(f"Upload successful: {file_name} -> {file_url}")
            
            # Make file publicly viewable (optional)
            try:
                self.service.permissions().create(
                    fileId=file_id,
                    body={'role': 'reader', 'type': 'anyone'}
                ).execute()
                logger.info(f"Made file public: {file_id}")
            except Exception as e:
                logger.warning(f"Could not make file public: {e}")

            return file_url

        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            return None

    def list_recordings(self, username, limit=10):
        """
        List recent recordings for a user from Google Drive
        
        Args:
            username (str): TikTok username
            limit (int): Maximum number of files to return
        
        Returns:
            list: List of file information dictionaries
        """
        try:
            # Get user folder
            main_folder_id = self.find_or_create_folder('TikTok Recordings')
            if not main_folder_id:
                return []

            user_folder_id = self.find_or_create_folder(username, main_folder_id)
            if not user_folder_id:
                return []

            # Search for video files in user's folders
            query = f"'{user_folder_id}' in parents and mimeType='video/mp4' and trashed=false"
            
            results = self.service.files().list(
                q=query,
                orderBy='createdTime desc',
                pageSize=limit,
                fields='files(id, name, createdTime, size, webViewLink, webContentLink)'
            ).execute()

            files = results.get('files', [])
            
            # Also check date subfolders
            date_folders_query = f"'{user_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            date_folders = self.service.files().list(
                q=date_folders_query,
                fields='files(id, name)'
            ).execute().get('files', [])

            # Search in date folders too
            for folder in date_folders:
                folder_query = f"'{folder['id']}' in parents and mimeType='video/mp4' and trashed=false"
                folder_files = self.service.files().list(
                    q=folder_query,
                    orderBy='createdTime desc',
                    pageSize=limit,
                    fields='files(id, name, createdTime, size, webViewLink, webContentLink)'
                ).execute().get('files', [])
                
                files.extend(folder_files)

            # Sort by creation time and limit
            files.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
            return files[:limit]

        except Exception as e:
            logger.error(f"Error listing recordings for {username}: {e}")
            return []

    def delete_file(self, file_id):
        """
        Delete a file from Google Drive
        
        Args:
            file_id (str): Google Drive file ID
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            return False

    def get_storage_usage(self):
        """
        Get Google Drive storage usage information
        
        Returns:
            dict: Storage usage information
        """
        try:
            about = self.service.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})
            
            return {
                'limit': int(quota.get('limit', 0)),
                'usage': int(quota.get('usage', 0)),
                'usageInDrive': int(quota.get('usageInDrive', 0)),
                'usageInDriveTrash': int(quota.get('usageInDriveTrash', 0))
            }
        except Exception as e:
            logger.error(f"Error getting storage usage: {e}")
            return {}