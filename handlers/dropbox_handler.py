# handlers/dropbox_handler.py

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import dropbox
from dropbox.exceptions import AuthError, ApiError
import webbrowser

from logger import get_logger


class DropboxHandler:
    """Handles Dropbox uploads with structured folder organization"""
    
    def __init__(self, app_key: Optional[str] = None, app_secret: Optional[str] = None, access_token: Optional[str] = None):
        self.logger = get_logger(__name__)
        self.dbx = None
        self.app_key = app_key
        self.app_secret = app_secret
        
        # Try access token first, then OAuth flow
        if access_token:
            if self._connect_with_token(access_token):
                return
        
        if app_key:
            self._initiate_oauth_flow()
        else:
            self.logger.info("No Dropbox credentials provided - uploads disabled")
    
    def _connect_with_token(self, access_token: str) -> bool:
        """Connect using existing access token"""
        try:
            self.dbx = dropbox.Dropbox(access_token)
            # Test connection
            self.dbx.users_get_current_account()
            self.logger.info("✅ Connected to Dropbox with existing token")
            return True
        except AuthError as e:
            self.logger.warning(f"⚠️ Existing Dropbox token invalid: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"⚠️ Dropbox connection failed with token: {e}")
            return False
    
    def _initiate_oauth_flow(self):
        """Initiate OAuth flow to get access token"""
        try:
            self.logger.info("🔐 Starting Dropbox OAuth flow...")
            
            # Create OAuth flow (with or without app secret)
            if self.app_secret:
                auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
                    self.app_key,
                    consumer_secret=self.app_secret,
                    use_pkce=True, 
                    token_access_type='offline'
                )
            else:
                auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
                    self.app_key, 
                    use_pkce=True, 
                    token_access_type='offline'
                )
            
            # Get authorization URL
            authorize_url = auth_flow.start()
            
            print("\n" + "="*60)
            print("🔐 DROPBOX AUTHENTICATION REQUIRED")
            print("="*60)
            print("1. Opening Dropbox authorization page in your browser...")
            print("2. Please authorize the application")
            print("3. Copy the authorization code from the page")
            print("4. Paste it below when prompted")
            print("="*60)
            
            # Open browser
            webbrowser.open(authorize_url)
            
            # Get authorization code from user
            auth_code = input("\n📋 Enter the authorization code from Dropbox: ").strip()
            
            if not auth_code:
                self.logger.warning("❌ No authorization code provided - Dropbox uploads disabled")
                return
            
            # Complete OAuth flow
            oauth_result = auth_flow.finish(auth_code)
            access_token = oauth_result.access_token
            
            # Connect with the new token
            self.dbx = dropbox.Dropbox(access_token)
            
            # Test connection
            account = self.dbx.users_get_current_account()
            self.logger.info(f"✅ Connected to Dropbox as: {account.name.display_name}")
            
            # Save token for future use
            print(f"\n💾 Save this access token for future use:")
            print(f"DROPBOX_ACCESS_TOKEN={access_token}")
            print("Add it to your .env file to skip this step next time\n")
            
        except Exception as e:
            self.logger.error(f"❌ Dropbox OAuth flow failed: {e}")
            self.dbx = None
    
    def extract_ticker_from_search_name(self, search_name: str) -> str:
        """Extract ticker name (first 4 letters) from search name"""
        # Remove common words and clean the search name
        clean_name = re.sub(r'\b(broker|reports?|analysis|research|the|and|for|with|from)\b', '', search_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'[^A-Za-z0-9\s]', '', clean_name).strip()
        
        # Get first word and take first 4 letters
        words = clean_name.split()
        if words:
            first_word = words[0].upper()
            return first_word[:4]
        
        # Final fallback: use cleaned search name first 4 letters
        fallback = re.sub(r'[^A-Za-z0-9]', '', search_name)
        return fallback[:4].upper()
    
    def get_dropbox_path(self, search_name: str, date: Optional[datetime] = None) -> str:
        """Generate Dropbox path: /<TICKER>/Broker Reports/<YYYY-MM-DD>/"""
        ticker = self.extract_ticker_from_search_name(search_name)
        
        if date is None:
            date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        
        path = f"/{ticker}/Broker Reports/{date_str}"
        return path
    
    def create_folder_structure(self, path: str) -> bool:
        """Create full folder structure in Dropbox if it doesn't exist"""
        if not self.dbx:
            return False
        
        # Split path into parts and create each level
        path_parts = [part for part in path.split('/') if part]
        current_path = ""
        
        for part in path_parts:
            current_path += f"/{part}"
            
            try:
                # Check if folder exists
                self.dbx.files_get_metadata(current_path)
                self.logger.debug(f"📁 Folder exists: {current_path}")
            except:
                # Folder doesn't exist, create it
                try:
                    self.dbx.files_create_folder_v2(current_path)
                    self.logger.info(f"📁 Created Dropbox folder: {current_path}")
                except Exception as create_error:
                    self.logger.error(f"❌ Failed to create folder {current_path}: {create_error}")
                    return False
        
        self.logger.info(f"✅ Full folder structure ready: {path}")
        return True
    
    def create_folder_if_not_exists(self, path: str) -> bool:
        """Create folder in Dropbox if it doesn't exist (legacy method)"""
        return self.create_folder_structure(path)
    
    def upload_folder(self, local_folder_path: Path, search_name: str) -> bool:
        """Upload individual files from folder to Dropbox with organized structure"""
        if not self.dbx:
            self.logger.warning("Dropbox not connected - skipping upload")
            return False
            
        if not local_folder_path.exists():
            self.logger.error(f"❌ Local folder not found: {local_folder_path}")
            return False
        
        try:
            # Generate Dropbox path
            dropbox_base_path = self.get_dropbox_path(search_name)
            
            # Check if date folder already exists - skip upload if it does
            try:
                self.dbx.files_get_metadata(dropbox_base_path)
                self.logger.info(f"📁 Date folder already exists in Dropbox, skipping upload: {dropbox_base_path}")
                # Clean up local folder since files are already in Dropbox
                self._cleanup_local_folder(local_folder_path)
                return True  # Return success since files are already there
            except:
                # Folder doesn't exist, proceed with upload
                pass
            
            # Create base folder structure
            if not self.create_folder_structure(dropbox_base_path):
                return False
            
            # Get all files in the folder (excluding directories)
            all_files = [f for f in local_folder_path.rglob('*') if f.is_file()]
            uploaded_files = 0
            total_files = len(all_files)
            
            self.logger.info(f"📤 Starting upload of {total_files} files to {dropbox_base_path}")
            
            for local_file in all_files:
                # Upload file directly to the base path (no subfolder structure)
                dropbox_file_path = f"{dropbox_base_path}/{local_file.name}"
                
                # Upload file
                if self._upload_file(local_file, dropbox_file_path):
                    uploaded_files += 1
                    self.logger.info(f"✅ Uploaded ({uploaded_files}/{total_files}): {local_file.name}")
                else:
                    self.logger.error(f"❌ Failed to upload: {local_file.name}")
            
            if uploaded_files == total_files:
                self.logger.info(f"🎉 Successfully uploaded all {uploaded_files} files to Dropbox!")
                # Clean up local folder after successful upload
                self._cleanup_local_folder(local_folder_path)
                return True
            else:
                self.logger.warning(f"⚠️ Partial upload: {uploaded_files}/{total_files} files uploaded")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error uploading folder {local_folder_path}: {e}")
            return False
    
    def _cleanup_local_folder(self, folder_path: Path) -> bool:
        """Remove local export folder after successful upload"""
        try:
            if folder_path.exists() and folder_path.is_dir():
                shutil.rmtree(folder_path)
                self.logger.info(f"🗑️ Cleaned up local folder: {folder_path.name}")
                return True
            return False
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to cleanup local folder {folder_path}: {e}")
            return False
    
    def _upload_file(self, local_file_path: Path, dropbox_file_path: str) -> bool:
        """Upload a single file to Dropbox"""
        try:
            file_size = local_file_path.stat().st_size
            
            with open(local_file_path, 'rb') as file:
                if file_size <= 150 * 1024 * 1024:  # 150MB - use simple upload
                    self.dbx.files_upload(
                        file.read(),
                        dropbox_file_path,
                        mode=dropbox.files.WriteMode('overwrite'),
                        autorename=False
                    )
                else:
                    # Use upload session for large files
                    self._upload_large_file(file, dropbox_file_path, file_size)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error uploading file {local_file_path}: {e}")
            return False
    
    def _upload_large_file(self, file, dropbox_file_path: str, file_size: int):
        """Upload large file using upload session"""
        CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks
        
        session_start_result = self.dbx.files_upload_session_start(file.read(CHUNK_SIZE))
        cursor = dropbox.files.UploadSessionCursor(
            session_id=session_start_result.session_id,
            offset=file.tell()
        )
        
        # Upload chunks
        while file.tell() < file_size:
            if (file_size - file.tell()) <= CHUNK_SIZE:
                # Final chunk
                self.dbx.files_upload_session_finish(
                    file.read(CHUNK_SIZE),
                    cursor,
                    dropbox.files.CommitInfo(path=dropbox_file_path, mode=dropbox.files.WriteMode('overwrite'))
                )
            else:
                # Regular chunk
                self.dbx.files_upload_session_append_v2(file.read(CHUNK_SIZE), cursor)
                cursor.offset = file.tell()
    
    def upload_multiple_folders(self, folder_paths: List[Path], search_name: str) -> dict:
        """Upload multiple folders and return results summary"""
        results = {
            'successful': [],
            'failed': [],
            'total': len(folder_paths)
        }
        
        if not self.dbx:
            self.logger.warning("Dropbox not connected - skipping all uploads")
            results['failed'] = folder_paths
            return results
        
        for folder_path in folder_paths:
            if self.upload_folder(folder_path, search_name):
                results['successful'].append(folder_path)
            else:
                results['failed'].append(folder_path)
        
        success_count = len(results['successful'])
        total_count = results['total']
        self.logger.info(f"📊 Upload summary: {success_count}/{total_count} folders uploaded successfully")
        
        return results
    
    def is_connected(self) -> bool:
        """Check if Dropbox connection is active"""
        return self.dbx is not None