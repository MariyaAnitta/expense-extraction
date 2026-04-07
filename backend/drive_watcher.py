"""
Google Drive Watcher Module
Monitors a shared Google Drive folder for new receipt uploads.
When a new file is detected, it downloads and processes it through the existing pipeline.
"""

import os
import io
import time
import tempfile
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- Configuration ---
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service():
    """Initialize Google Drive API service using Service Account credentials."""
    import json
    
    # Option 1: Read from environment variable (for Render deployment)
    creds_json_str = os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON")
    if creds_json_str:
        try:
            creds_dict = json.loads(creds_json_str)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            service = build('drive', 'v3', credentials=credentials)
            print("Google Drive API service initialized from env var.")
            return service
        except Exception as e:
            print(f"Failed to init Drive from env var: {e}")
    
    # Option 2: Read from local JSON file (for local development)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    creds_path = os.path.join(current_dir, 'cash-portal-97361-95a39c505149.json')
    
    if not os.path.exists(creds_path):
        creds_path = os.getenv("GOOGLE_DRIVE_CREDENTIALS", creds_path)
    
    if not os.path.exists(creds_path):
        print("WARNING: Google Drive credentials not found (env var or file). Drive integration disabled.")
        return None
        
    credentials = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )
    service = build('drive', 'v3', credentials=credentials)
    print("Google Drive API service initialized from local file.")
    return service


def register_watch(service, folder_id: str, webhook_url: str, channel_id: str = "expense-drive-watch"):
    """
    Register a push notification channel to watch a Google Drive folder.
    Google will send POST requests to webhook_url when files change.
    
    Note: Watch channels expire (default ~1 hour). 
    A background task should periodically re-register.
    """
    try:
        body = {
            'id': channel_id,
            'type': 'web_hook',
            'address': webhook_url,
            'expiration': int((time.time() + 86400) * 1000)  # 24 hours from now (in ms)
        }
        
        # Watch changes on the specific folder
        response = service.files().watch(
            fileId=folder_id,
            body=body
        ).execute()
        
        print(f"Drive Watch registered successfully!")
        print(f"  Channel ID: {response.get('id')}")
        print(f"  Resource ID: {response.get('resourceId')}")
        print(f"  Expiration: {response.get('expiration')}")
        
        return response
    except Exception as e:
        print(f"Failed to register Drive watch: {e}")
        return None


def list_new_files(service, folder_id: str, since_time: Optional[float] = None):
    """
    List files in the watched folder, optionally filtering by modification time.
    Returns list of file metadata dicts.
    """
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        
        if since_time:
            from datetime import datetime
            time_str = datetime.utcfromtimestamp(since_time).isoformat() + 'Z'
            query += f" and modifiedTime > '{time_str}'"
        
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType, createdTime, modifiedTime)",
            orderBy="createdTime desc",
            pageSize=50
        ).execute()
        
        files = results.get('files', [])
        print(f"Found {len(files)} files in Drive folder.")
        return files
    except Exception as e:
        print(f"Error listing Drive files: {e}")
        return []


def download_file(service, file_id: str, file_name: str) -> Optional[str]:
    """
    Download a file from Google Drive to a temporary local path.
    Returns the local file path, or None on failure.
    """
    try:
        # For Google Docs types (like scanned PDFs), export as PDF
        request = service.files().get_media(fileId=file_id)
        
        uploads_dir = os.path.join(tempfile.gettempdir(), "receipt_uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        local_path = os.path.join(uploads_dir, f"drive_{file_id}_{file_name}")
        
        fh = io.FileIO(local_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"Download progress: {int(status.progress() * 100)}%")
        
        fh.close()
        print(f"Downloaded: {file_name} -> {local_path}")
        return local_path
        
    except Exception as e:
        print(f"Error downloading file {file_name}: {e}")
        return None
