# handlers/__init__.py
"""
Handler modules for AlphaSense Scraper

This package contains specialized handlers for different aspects of the scraping process:
- browser_manager: Browser setup and navigation
- ui_handler: UI interactions and element manipulation  
- file_handler: File operations and ZIP extraction
- cache_manager: Data caching and persistence
"""

from .browser_manager import BrowserManager
from .ui_handler import UIHandler
from .file_handler import FileHandler
from .cache_manager import CacheManager
from .dropbox_handler import DropboxHandler

__all__ = ['BrowserManager', 'UIHandler', 'FileHandler', 'CacheManager', 'DropboxHandler']