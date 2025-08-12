# scraper_refactored.py

import time
from bs4 import BeautifulSoup

from config import Config
from logger import get_logger
from handlers import BrowserManager, UIHandler, FileHandler, CacheManager, DropboxHandler


class AlphaSenseScraper:
    """Refactored core scraper class for AlphaSense saved search exports"""
    
    def __init__(self, config: Config, headless: bool = True, dropbox_app_key: str = None, dropbox_app_secret: str = None, dropbox_token: str = None):
        self.config = config
        self.logger = get_logger(__name__)
        self.collected_row_data = []
        
        # Initialize all components
        self.browser = BrowserManager(config, headless)
        self.ui = UIHandler(self.browser)
        self.files = FileHandler(self.browser)
        self.cache = CacheManager()
        self.dropbox = DropboxHandler(app_key=dropbox_app_key, app_secret=dropbox_app_secret, access_token=dropbox_token)
    
    def close(self) -> None:
        """Close the scraper and all components"""
        self.browser.close()
    
    def login(self, username: str, password: str) -> bool:
        """Login to AlphaSense"""
        return self.browser.login(username, password)
    
    def collect_all_data(self, search_id: str, target_rows: int = 200) -> str:
        """Collect all available data from a search and save to cache"""
        try:
            self.logger.info(f"🔍 Collecting data for search ID: {search_id}")
            alphasense_config = self.config.get_alphasense_config()
            base_url = alphasense_config.get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            
            self.browser.navigate_to(search_url)

            if not self.browser.wait_for_results():
                raise Exception("Results did not load")

            self.logger.info("Starting data collection phase...")
            total_collected = self._scroll_to_load_more_rows(target_rows=target_rows)  
            
            if total_collected == 0:
                raise Exception("No data collected")
            
            # Save the collected data to cache file
            cache_file = self.cache.save_to_cache(search_id, self.collected_row_data)
            
            self.logger.info(f"Data collection complete! Collected {total_collected} rows")
            return cache_file
            
        except Exception as e:
            self.logger.error(f"Error during data collection: {e}")
            raise
    
    def _scroll_to_load_more_rows(self, target_rows: int = 121) -> int:
        """Scroll through results to load more rows and collect their data"""
        scrollable_container = self.ui.get_scrollable_container()

        # Initialize tracking variables
        all_row_data = []
        seen_document_ids = set()
        scroll_attempts = 0
        max_scroll_attempts = 30
        consecutive_no_new_items = 0
        max_consecutive = 8
        
        # Different scrolling strategies to try
        strategies = [
            "keyboard_navigation", 
            "scroll_container", 
            "scroll_window", 
            "click_last_row",
            "page_down_keys"
        ]
        current_strategy = 0
        
        while len(all_row_data) < target_rows and scroll_attempts < max_scroll_attempts:
            scroll_attempts += 1
            
            # Parse the current page to find result rows
            html = self.browser.driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            row_divs = soup.find_all("div", {"data-testid": "ResultsListRow"})
            
            # Process each row found on the page
            batch_new_items = 0
            for row in row_divs:
                doc_div = row.find("div", {"data-cy-document-id": True})
                document_id = doc_div["data-cy-document-id"] if doc_div else None
                
                # Only process new documents (not duplicates)
                if document_id and document_id not in seen_document_ids:
                    seen_document_ids.add(document_id)
                    batch_new_items += 1
                    
                    # Extract all data fields from the row
                    row_index = row.get("data-cy-rowindex")
                    source = row.find(attrs={'data-testid': 'resultsPaneCell-source'})
                    author = row.find(attrs={'data-testid': 'resultsPaneCell-author'})
                    page_count = row.find(attrs={'data-testid': 'resultsPaneCell-pageCount'})
                    score = row.find(attrs={'data-cy': 'score'})
                    release_date = row.find(attrs={'data-cy': 'releaseDate'})
                    title = row.find(attrs={'data-testid': 'resultsPaneCell-title'})
                    ticker = row.find(attrs={'data-testid': 'resultsPaneCell-ticker'})
                    company = row.find(attrs={'data-testid': 'resultsPaneCell-company'})

                    # Create a data object for this row
                    row_data = {
                        'row_index': row_index,
                        'document_id': document_id,
                        'source': source.text.strip() if source else None,
                        'author': author.text.strip() if author else None,
                        'page_count': page_count.text.strip() if page_count else None,
                        'score': score.get('data-score') if score else None,
                        'release_date': release_date.text.strip() if release_date else None,
                        'title': title.text.strip() if title else None,
                        'ticker': ticker.text.strip() if ticker else None,
                        'company': company.text.strip() if company else None,
                    }
                    all_row_data.append(row_data)
            
            if batch_new_items > 0:
                self.logger.info(f"Found {batch_new_items} new results. Total collected: {len(all_row_data)}")
            
            if batch_new_items == 0:
                consecutive_no_new_items += 1
                
                if consecutive_no_new_items >= max_consecutive:
                    self.logger.info("Multiple consecutive attempts with no new items, trying next strategy or stopping")
                    current_strategy += 1
                    if current_strategy >= len(strategies):
                        self.logger.info("All strategies exhausted, stopping")
                        break
                    else:
                        consecutive_no_new_items = 0  
                strategy = strategies[current_strategy % len(strategies)]
                
                # Try different scrolling methods
                if strategy == "scroll_container":
                    for _ in range(5):
                        self.browser.driver.execute_script(
                            "arguments[0].scrollTop += arguments[0].clientHeight * 2;", 
                            scrollable_container
                        )
                        time.sleep(0.3)
                
                elif strategy == "scroll_window":
                    for _ in range(3):
                        self.browser.driver.execute_script("window.scrollBy(0, 1000);")
                        time.sleep(0.3)
                
            else:
                consecutive_no_new_items = 0 
                current_strategy = 0 
                
                self.browser.driver.execute_script(
                    "arguments[0].scrollTop += arguments[0].clientHeight * 0.8;", 
                    scrollable_container
                )
                time.sleep(0.4)
        
        self.logger.info(f"Collected {len(all_row_data)} total unique rows after {scroll_attempts} attempts")
        
        # Store collected data
        self.collected_row_data = all_row_data
        
        return len(all_row_data)
    
    def export_first_n_in_search(self, search_id: str, n: int = 20) -> bool:
        """Export the first n documents from a search"""
        try:
            self.logger.info(f"🔎 Exporting first {n} docs from search {search_id}")

            # Navigate to search results page
            base_url = self.config.get_alphasense_config().get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            self.browser.navigate_to(search_url)

            if not self.browser.wait_for_results(timeout=20):
                raise Exception("Results did not load")

            # Select checkboxes for first n rows
            selected = self.ui.select_first_n_checkboxes(n=n)
            if selected == 0:
                self.logger.error("No rows were selected — aborting export.")
                return False
            elif selected < n:
                self.logger.info(f"Selected {selected} rows (fewer than requested {n}) — proceeding with export.")

            # Click export 
            if not self.ui.click_export_button():
                self.logger.error("Export button not found/click failed.")
                return False

            downloaded_files = self.files.wait_for_download(timeout=90)
            if downloaded_files:
                self.logger.info("Export started and file detected in downloads.")
                
                # Get search name and extract ZIP files
                search_name = self.cache.get_search_name_from_csv(search_id)
                extracted_folders = self.files.extract_zip_files(downloaded_files, search_name)
                self.logger.info(f"Extracted {len(extracted_folders)} ZIP files into organized folders with search name: {search_name}")
                
                # Upload to Dropbox if connected
                if self.dropbox.is_connected() and extracted_folders:
                    self.logger.info("📤 Uploading to Dropbox...")
                    upload_results = self.dropbox.upload_multiple_folders(extracted_folders, search_name)
                    if upload_results['successful']:
                        self.logger.info(f"✅ Successfully uploaded {len(upload_results['successful'])} folders to Dropbox")
                    if upload_results['failed']:
                        self.logger.warning(f"⚠️ Failed to upload {len(upload_results['failed'])} folders to Dropbox")
                
                return True
            else:
                self.logger.warning("Export attempted, but no download detected within timeout.")
                return False
        except Exception as e:
            self.logger.error(f"Failed export_first_n_in_search: {e}")
            return False
    
    def export_from_cache(self, cache_file: str, bundle_size: int = 20) -> list:
        """Export documents using previously cached data, processing in bundles"""
        try:
            # Load cached data
            cache_data = self.cache.load_from_cache(cache_file)
            rows = cache_data['rows']
            search_id = cache_data['search_id']
            
            self.logger.info(f"Starting export phase for {len(rows)} rows in bundles of {bundle_size}")
            
            # Navigate to search results page
            alphasense_config = self.config.get_alphasense_config()
            base_url = alphasense_config.get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            self.browser.navigate_to(search_url)
            
            if not self.browser.wait_for_results():
                raise Exception("Results did not load")
            
            scrollable_container = self.ui.get_scrollable_container()
            exported_files = []
            
            # Process the rows in bundles
            for bundle_start in range(0, len(rows), bundle_size):
                bundle_end = min(bundle_start + bundle_size, len(rows))
                bundle_rows = rows[bundle_start:bundle_end]
                
                self.logger.info(f"Processing bundle {bundle_start//bundle_size + 1}: rows {bundle_start}-{bundle_end-1}")
                
                # Reset scroll position and clear checkboxes
                self.browser.driver.execute_script("arguments[0].scrollTop = 0;", scrollable_container)
                time.sleep(1)
                self.ui.clear_all_checkboxes()
                
                selected_count = 0
                for row_data in bundle_rows:
                    row_index = row_data.get('row_index')
                    if not row_index:
                        continue
                    
                    try:
                        row_index_int = int(row_index)
                        self.logger.info(f"Selecting row {row_index_int}")
                        
                        if self.ui.scroll_to_specific_row_index(row_index_int, scrollable_container):
                            if self.ui.select_checkbox_for_visible_row(row_index_int):
                                selected_count += 1
                                self.logger.info(f"Selected row {row_index_int} ({selected_count}/{len(bundle_rows)})")
                            else:
                                self.logger.warning(f"Failed to select row {row_index_int}")
                        else:
                            self.logger.warning(f"Could not scroll to row {row_index_int}")
                            
                        time.sleep(0.3)
                        
                    except (ValueError, TypeError):
                        self.logger.warning(f"Invalid row index: {row_index}")
                        continue
                
                self.logger.info(f"Bundle selection complete: {selected_count}/{len(bundle_rows)} rows selected")
                
                # Export this bundle if we have selected rows
                if selected_count >= 1: 
                    if self.ui.click_export_button():
                        time.sleep(1)  # Brief wait for export to start
                        
                        downloaded_files = self.files.wait_for_download(timeout=60)
                        if downloaded_files:
                            bundle_num = bundle_start//bundle_size + 1
                            self.logger.info(f"Bundle {bundle_num} exported successfully!")
                            
                            # Get search name and extract ZIP files with bundle number
                            search_name = self.cache.get_search_name_from_csv(search_id)
                            extracted_folders = self.files.extract_zip_files(downloaded_files, search_name, bundle_num)
                            self.logger.info(f"Extracted {len(extracted_folders)} ZIP files for bundle {bundle_num} with search name: {search_name}")
                            
                            # Upload to Dropbox if connected
                            if self.dropbox.is_connected() and extracted_folders:
                                self.logger.info(f"📤 Uploading bundle {bundle_num} to Dropbox...")
                                upload_results = self.dropbox.upload_multiple_folders(extracted_folders, search_name)
                                if upload_results['successful']:
                                    self.logger.info(f"✅ Bundle {bundle_num}: uploaded {len(upload_results['successful'])} folders to Dropbox")
                                if upload_results['failed']:
                                    self.logger.warning(f"⚠️ Bundle {bundle_num}: failed to upload {len(upload_results['failed'])} folders")
                            
                            exported_files.append(f"bundle_{bundle_num}")
                        else:
                            self.logger.warning(f"Bundle {bundle_start//bundle_size + 1} export attempted but no download detected")
                            exported_files.append(f"bundle_{bundle_start//bundle_size + 1}_partial")
                    else:
                        self.logger.error(f"Failed to export bundle {bundle_start//bundle_size + 1}")
                else:
                    self.logger.error(f"No rows selected for bundle {bundle_start//bundle_size + 1}")
                
                time.sleep(2)
            
            self.logger.info(f"🎉 Export complete! Processed {len(exported_files)} bundles")
            return exported_files
            
        except Exception as e:
            self.logger.error(f"Error during export from cache: {e}")
            return []
    
    def export_saved_search(self, search_id: str, max_results: int = 100) -> list:
        """Run the complete export process for a search"""
        try:
            self.logger.info(f"Starting complete export process for search {search_id}")
            
            # Phase 1: Collect all data and save to cache
            self.logger.info("Phase 1: Collecting all data...")
            cache_file = self.collect_all_data(search_id, target_rows=max_results)
            
            # Phase 2: Export using cached data in bundles
            self.logger.info("Phase 2: Exporting in bundles...")
            exported_files = self.export_from_cache(cache_file, bundle_size=20)
            
            if exported_files:
                self.logger.info(f"Complete export successful! {len(exported_files)} bundles exported")
                return exported_files
            else:
                self.logger.error("No files were exported")
                return []
                
        except Exception as e:
            self.logger.error(f"Error in complete export process: {e}")
            return []
    
    def resume_export_from_cache(self, cache_file: str) -> list:
        """Resume an export using a previously saved cache file"""
        self.logger.info(f"Resuming export from cache file: {cache_file}")
        return self.export_from_cache(cache_file, bundle_size=20)
    
    def list_cache_files(self) -> list:
        """List all available cache files"""
        return self.cache.list_cache_files()
    
    def debug_checkbox_structure(self, max_rows: int = 3) -> None:
        """Debug method to examine checkbox structure on the page"""
        return self.ui.debug_checkbox_structure(max_rows)