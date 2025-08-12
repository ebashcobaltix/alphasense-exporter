# file_handler.py

import time
import zipfile
import shutil
from datetime import datetime
from pathlib import Path

from logger import get_logger


class FileHandler:
    """Handles file operations like download detection and ZIP extraction"""
    
    def __init__(self, browser_manager):
        self.browser = browser_manager
        self.logger = get_logger(__name__)
    
    def wait_for_download(self, download_dir: str = None, timeout: int = 30) -> list:
        """Wait for a file to be downloaded to the specified directory"""
        if download_dir is None:
            download_dir = self.browser.get_download_dir()
        
        download_path = Path(download_dir).resolve()
        self.logger.info(f"Monitoring download directory: {download_path}")
        
        initial_files = set(download_path.glob('*')) if download_path.exists() else set()
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if download_path.exists():
                current_files = set(download_path.glob('*'))
                new_files = current_files - initial_files
                # Only check for completed ZIP files
                zip_files = [f for f in new_files if f.name.lower().endswith('.zip')]
                if zip_files:
                    self.logger.info(f"ZIP download completed: {[f.name for f in zip_files]}")
                    return zip_files
            time.sleep(1)
        
        self.logger.warning(f"No download detected within {timeout}s timeout. Checked directory: {download_path}")
        return []
    
    def extract_zip_files(self, downloaded_files: list, search_name: str, bundle_num: int = None) -> list:
        """Extract ZIP files into organized folders and clean up"""
        extracted_folders = []
        
        for file_path in downloaded_files:
            if file_path.suffix.lower() != '.zip':
                self.logger.info(f"Skipping non-ZIP file: {file_path.name}")
                continue
                
            try:
                # Create extraction folder name with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                if bundle_num is not None:
                    folder_name = f"{search_name}_bundle{bundle_num}_{timestamp}"
                else:
                    folder_name = f"{search_name}_{timestamp}"
                
                # Create unique folder name if it already exists
                extraction_folder = file_path.parent / folder_name
                counter = 1
                while extraction_folder.exists():
                    if bundle_num is not None:
                        extraction_folder = file_path.parent / f"{search_name}_bundle{bundle_num}_{timestamp}_{counter}"
                    else:
                        extraction_folder = file_path.parent / f"{search_name}_{timestamp}_{counter}"
                    counter += 1
                
                # Create the extraction folder
                extraction_folder.mkdir(parents=True, exist_ok=True)
                
                # Extract ZIP file
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extraction_folder)
                    extracted_files = zip_ref.namelist()
                    self.logger.info(f"Extracted {len(extracted_files)} files from {file_path.name} to {extraction_folder.name}")
                
                # Clean up extracted files
                self._cleanup_extracted_files(extraction_folder)
                
                # Remove the original ZIP file
                file_path.unlink()
                self.logger.info(f"Removed original ZIP file: {file_path.name}")
                
                extracted_folders.append(extraction_folder)
                
            except Exception as e:
                self.logger.error(f"Error extracting ZIP file {file_path}: {e}")
                continue
        
        return extracted_folders
    
    def _cleanup_extracted_files(self, folder_path: Path) -> None:
        """Clean up extracted files by removing system folders and organizing content"""
        try:
            # Remove __MACOSX folders
            for macosx_folder in folder_path.rglob("__MACOSX"):
                if macosx_folder.is_dir():
                    shutil.rmtree(macosx_folder, ignore_errors=True)
                    self.logger.info(f"Removed __MACOSX folder: {macosx_folder}")
            
            # Remove .DS_Store files
            for ds_store in folder_path.rglob(".DS_Store"):
                if ds_store.is_file():
                    ds_store.unlink()
                    self.logger.info(f"Removed .DS_Store file: {ds_store}")
            
            # Move files from nested folders to root if there's only one subfolder
            subfolders = [item for item in folder_path.iterdir() if item.is_dir()]
            if len(subfolders) == 1:
                subfolder = subfolders[0]
                # Move all files from subfolder to parent
                for item in subfolder.rglob("*"):
                    if item.is_file():
                        try:
                            relative_path = item.relative_to(subfolder)
                            target_path = folder_path / relative_path
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Handle name conflicts
                            if target_path.exists():
                                stem, suffix = target_path.stem, target_path.suffix
                                counter = 1
                                while target_path.exists():
                                    target_path = folder_path / f"{stem}_{counter}{suffix}"
                                    counter += 1
                            
                            item.rename(target_path)
                        except Exception as e:
                            self.logger.warning(f"Could not move file {item}: {e}")
                
                # Remove the now-empty subfolder
                shutil.rmtree(subfolder, ignore_errors=True)
                self.logger.info(f"Flattened folder structure from {subfolder.name}")
                
        except Exception as e:
            self.logger.error(f"Error cleaning up extracted files: {e}")