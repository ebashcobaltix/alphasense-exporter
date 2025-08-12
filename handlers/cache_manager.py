# cache_manager.py

import json
import csv
import re
from datetime import datetime
from pathlib import Path

from logger import get_logger


class CacheManager:
    """Handles caching and data persistence for scraping results"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.cache_dir = Path('./cache')
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_cache_filename(self, search_id: str) -> str:
        """Generate a unique filename for caching search results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"search_{search_id}_{timestamp}.json"
    
    def save_to_cache(self, search_id: str, data: list) -> str:
        """Save collected data to a cache file for later use"""
        cache_file = self.cache_dir / self.get_cache_filename(search_id)
        
        cache_data = {
            'search_id': search_id,
            'collected_at': datetime.now().isoformat(),
            'total_rows': len(data),
            'rows': data
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Saved {len(data)} rows to cache: {cache_file}")
        return str(cache_file)
    
    def load_from_cache(self, cache_file: str) -> dict:
        """Load previously saved data from the cache file"""
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.logger.info(f"Loaded {data['total_rows']} rows from cache: {cache_file}")
        return data
    
    def list_cache_files(self) -> list:
        """List all available cache files"""
        cache_files = list(self.cache_dir.glob('search_*.json'))
        self.logger.info(f"Found {len(cache_files)} cache files:")
        for cache_file in cache_files:
            self.logger.info(f"  - {cache_file.name}")
        return [str(f) for f in cache_files]
    
    def get_search_name_from_csv(self, search_id: str, csv_path: str = './saved_searches.csv') -> str:
        """Get search name from CSV file based on search_id"""
        try:
            csv_file_path = Path(csv_path)
            if not csv_file_path.exists():
                self.logger.warning(f"CSV file not found: {csv_path}")
                return f"search_{search_id[:8]}"
            
            with open(csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('search_id') == search_id:
                        search_name = row.get('search_name', '').strip()
                        # Clean search name for filename use
                        search_name = re.sub(r'[^\w\s-]', '', search_name)
                        search_name = re.sub(r'\s+', '_', search_name)
                        return search_name if search_name else f"search_{search_id[:8]}"
            
            self.logger.warning(f"Search ID {search_id} not found in CSV")
            return f"search_{search_id[:8]}"
            
        except Exception as e:
            self.logger.error(f"Error reading CSV file: {e}")
            return f"search_{search_id[:8]}"