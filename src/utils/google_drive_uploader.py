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
                'mimeType': 'application/vnd.google-