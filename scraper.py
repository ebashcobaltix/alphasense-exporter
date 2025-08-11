import time
import os
import json
import zipfile
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementNotInteractableException
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from config import Config
from logger import get_logger


class AlphaSenseScraper:
    """AlphaSense scraper with cached export strategy + simple 'export first N' path"""
    
    def __init__(self, config: Config, headless: bool = True):
        self.config = config
        self.logger = get_logger(__name__)
        self.driver = None
        self.headless = headless
        self.collected_row_data = []
        self.cache_dir = Path('./cache')
        self.cache_dir.mkdir(exist_ok=True)
        
        self._setup_browser()
    
    def _setup_browser(self) -> None:
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        
        browser_config = self.config.get_browser_config()
        window_size = browser_config.get('window_size', {'width': 1920, 'height': 1080})
        chrome_options.add_argument(f'--window-size={window_size["width"]},{window_size["height"]}')
        
        user_agent = browser_config.get('user_agent')
        if user_agent:
            chrome_options.add_argument(f'--user-agent={user_agent}')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')

        download_dir = self.config.get('scraping.download_dir') or self.config.get('scraping.output_dir') or './exports'
        download_dir_path = str(Path(download_dir).resolve())
        prefs = {
            "download.default_directory": download_dir_path,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            self.logger.warning(f"Could not use webdriver-manager: {e}")
            self.driver = webdriver.Chrome(options=chrome_options)

        timeout = browser_config.get('timeout', 30)
        implicit_wait = browser_config.get('implicit_wait', 10)
        self.driver.implicitly_wait(implicit_wait)
        self.wait = WebDriverWait(self.driver, timeout)

        self.logger.info(f"Browser setup completed. Download directory: {download_dir_path}")
    
    def close(self) -> None:
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser closed")

    def login(self, username: str, password: str) -> bool:
        self.driver.get("https://research.alpha-sense.com/login")
        
        self.logger.info("Entering username")

        try:
            username_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='loginUsername']")))
            username_field.clear()
            username_field.send_keys(username)
        except TimeoutException:
            self.logger.error("Could not find username/email field")
            return False

        self.logger.info("Pressing continue")

        try:
            continue_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Continue')]")
            continue_button.click()
        except NoSuchElementException:
            self.logger.error("Could not find Continue button")
            return False

        self.logger.info("Entering password")

        try:
            password_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            password_field.clear()
            password_field.send_keys(password)
        except TimeoutException:
            self.logger.error("Could not find password field")
            return False

        try:
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='loginSubmitButton']")
            submit_button.click()
        except NoSuchElementException:
            self.logger.error("Could not find submit button")
            return False

        if self._is_logged_in():
            self.logger.info("Login successful")
            return True
        else:
            self.logger.error("Login failed - could not verify successful login")
            return False

    def _is_logged_in(self) -> bool:
        try:
            for xpath in [
                "//div[contains(@class, 'dashboard')]",
                "//div[contains(@class, 'search')]",
            ]:
                try:
                    if self.driver.find_element(By.XPATH, xpath).is_displayed():
                        return True
                except NoSuchElementException:
                    continue
            return 'login' not in self.driver.current_url.lower()
        except Exception as e:
            self.logger.warning(f"Could not determine login status: {e}")
            return False

    def _wait_for_results(self, timeout: int = 20) -> bool:
        """Sturdier wait that tolerates slow paint, ensures at least one row exists."""
        try:
            self.wait.until(EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')),
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="ResultsList"]'))
            ))
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
            )
            self.logger.info("✅ Results loaded")
            return True
        except TimeoutException:
            self.logger.error("❌ Results did not load")
            return False

    def _get_cache_filename(self, search_id: str) -> str:
        """Generate cache filename for search results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"search_{search_id}_{timestamp}.json"

    def _save_to_cache(self, search_id: str, data: list) -> str:
        """Save collected data to cache file"""
        cache_file = self.cache_dir / self._get_cache_filename(search_id)
        
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

    def _load_from_cache(self, cache_file: str) -> dict:
        """Load data from cache file"""
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.logger.info(f"📂 Loaded {data['total_rows']} rows from cache: {cache_file}")
        return data

    def _get_scrollable_container(self):
        """Find the scrollable container for the virtualized list (robust against wrappers)."""
        candidates = [
            '[data-testid="ResultsList"] [class*="simplebar-content-wrapper"]',
            'div[name="ResultList"] div[style*="overflow"]',
            'div[name="ResultList"]',
        ]
        for css in candidates:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, css)
                self.logger.info(f"Found scrollable container via: {css}")
                return el
            except NoSuchElementException:
                continue
        self.logger.warning("Could not find scrollable container, using body")
        return self.driver.find_element(By.TAG_NAME, 'body')

    # --------- JS helpers to avoid stale element references ---------

    def _get_scrollable_container_js(self):
        """Return the scrollable container via JS each time (no Python element refs)."""
        return self.driver.execute_script("""
            let c =
              document.querySelector('[data-testid="ResultsList"] [class*="simplebar-content-wrapper"]') ||
              document.querySelector('div[name="ResultList"] div[style*="overflow"]') ||
              document.querySelector('div[name="ResultList"]');
            return c || document.body;
        """)

    def _scroll_row_into_view_js(self, row_index: int) -> bool:
        """
        Make row with data-cy-rowindex == row_index render & be visible.
        Works with virtualized lists by incrementally scrolling until found.
        """
        for _ in range(18):  # up to ~18 'pages'
            found = self.driver.execute_script("""
                const idx = arguments[0];
                const sel = `div[data-testid="ResultsListRow"][data-cy-rowindex="${idx}"]`;
                const row = document.querySelector(sel);
                if (row) {
                    row.scrollIntoView({block: 'center'});
                    return true;
                }
                let c =
                  document.querySelector('[data-testid="ResultsList"] [class*="simplebar-content-wrapper"]') ||
                  document.querySelector('div[name="ResultList"] div[style*="overflow"]') ||
                  document.querySelector('div[name="ResultList"]') ||
                  document.body;
                c.scrollTop += c.clientHeight * 0.92;
                return false;
            """, row_index)
            if found:
                return True
            time.sleep(0.25)
        return False

    def _scroll_to_load_more_rows(self, target_rows: int = 121) -> int:
        """Scroll through virtualized list and collect data in batches"""
        scrollable_container = self._get_scrollable_container()

        all_row_data = []
        seen_document_ids = set()
        scroll_attempts = 0
        max_scroll_attempts = 30
        consecutive_no_new_items = 0
        max_consecutive = 8
        
        # Try different loading strategies
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
            
            # Parse current batch of visible rows
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            row_divs = soup.find_all("div", {"data-testid": "ResultsListRow"})
            
            batch_new_items = 0
            for row in row_divs:
                doc_div = row.find("div", {"data-cy-document-id": True})
                document_id = doc_div["data-cy-document-id"] if doc_div else None
                
                # Skip if we've already seen this document
                if document_id and document_id not in seen_document_ids:
                    seen_document_ids.add(document_id)
                    batch_new_items += 1
                    
                    row_index = row.get("data-cy-rowindex")
                    source = row.find(attrs={'data-testid': 'resultsPaneCell-source'})
                    author = row.find(attrs={'data-testid': 'resultsPaneCell-author'})
                    page_count = row.find(attrs={'data-testid': 'resultsPaneCell-pageCount'})
                    score = row.find(attrs={'data-cy': 'score'})
                    release_date = row.find(attrs={'data-cy': 'releaseDate'})
                    title = row.find(attrs={'data-testid': 'resultsPaneCell-title'})
                    ticker = row.find(attrs={'data-testid': 'resultsPaneCell-ticker'})
                    company = row.find(attrs={'data-testid': 'resultsPaneCell-company'})

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
            
            # Track consecutive attempts with no new items
            if batch_new_items == 0:
                consecutive_no_new_items += 1
                
                if consecutive_no_new_items >= max_consecutive:
                    self.logger.info("Multiple consecutive attempts with no new items, trying next strategy or stopping")
                    current_strategy += 1
                    if current_strategy >= len(strategies):
                        self.logger.info("All strategies exhausted, stopping")
                        break
                    else:
                        consecutive_no_new_items = 0  # Reset for new strategy
                
                # Try different loading strategies
                strategy = strategies[current_strategy % len(strategies)]
                
                if strategy == "scroll_container":
                    # Aggressive container scrolling
                    for i in range(5):
                        self.driver.execute_script(
                            "arguments[0].scrollTop += arguments[0].clientHeight * 2;", 
                            scrollable_container
                        )
                        time.sleep(0.3)
                
                elif strategy == "scroll_window":
                    # Window scrolling
                    for i in range(3):
                        self.driver.execute_script("window.scrollBy(0, 1000);")
                        time.sleep(0.3)
                
                # other strategies could be added similarly
                        
            else:
                consecutive_no_new_items = 0 
                current_strategy = 0  # Reset to first strategy
                
                # Normal scroll when we're finding new items
                self.driver.execute_script(
                    "arguments[0].scrollTop += arguments[0].clientHeight * 0.8;", 
                    scrollable_container
                )
                time.sleep(0.4)
        
        self.logger.info(f"Collected {len(all_row_data)} total unique rows after {scroll_attempts} attempts")
        
        # Store the collected data for later use
        self.collected_row_data = all_row_data
        
        return len(all_row_data)

    def _scroll_to_specific_row_index(self, target_row_index: int, scrollable_container) -> bool:
        """
        Scroll to make a specific row index visible in the virtualized list
        Returns True if row is found and visible, False otherwise
        """
        max_attempts = 15
        
        for attempt in range(max_attempts):
            try:
                # Get currently visible rows
                visible_rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
                
                # Check current visible range
                current_visible_indexes = []
                for row in visible_rows:
                    row_index = row.get_attribute('data-cy-rowindex')
                    if row_index:
                        try:
                            current_visible_indexes.append(int(row_index))
                        except ValueError:
                            continue
                
                if not current_visible_indexes:
                    self.logger.warning(f"No visible row indexes found on attempt {attempt + 1}")
                    continue
                
                min_visible = min(current_visible_indexes)
                max_visible = max(current_visible_indexes)
                
                # Check if target row is already visible
                if min_visible <= target_row_index <= max_visible:
                    self.logger.info(f"✅ Target row {target_row_index} is visible (range: {min_visible}-{max_visible})")
                    return True
                
                # Calculate scroll direction and amount
                if target_row_index < min_visible:
                    # Need to scroll up
                    scroll_amount = -(scrollable_container.size['height'] // 2)
                    self.logger.info(f"🔼 Scrolling up to reach row {target_row_index} (currently {min_visible}-{max_visible})")
                else:
                    # Need to scroll down
                    scroll_amount = scrollable_container.size['height'] // 2
                    self.logger.info(f"🔽 Scrolling down to reach row {target_row_index} (currently {min_visible}-{max_visible})")
                
                # Perform scroll
                self.driver.execute_script(
                    "arguments[0].scrollTop += arguments[1];", 
                    scrollable_container, 
                    scroll_amount
                )
                time.sleep(0.8)  # Give time for virtualized list to update
                
            except Exception as e:
                self.logger.warning(f"Error in scroll attempt {attempt + 1} for row {target_row_index}: {e}")
                time.sleep(0.5)
        
        self.logger.error(f"❌ Failed to make row {target_row_index} visible after {max_attempts} attempts")
        return False

    def _select_checkbox_in_row(self, row) -> bool:
        """
        Hover to reveal the checkbox, then click (with JS/React-friendly fallbacks).
        Returns True if selected.
        """
        try:
            # Hover often reveals row actions/checkbox
            try:
                ActionChains(self.driver).move_to_element(row).pause(0.15).perform()
            except Exception:
                pass

            checkbox = None
            for sel in [
                'input[data-chmlnid="ResultListDocumentCheckbox"]',
                'div[data-testid="resultsPaneCell-checkbox"] input[type="checkbox"]',
                'input[type="checkbox"]'
            ]:
                try:
                    checkbox = row.find_element(By.CSS_SELECTOR, sel)
                    break
                except NoSuchElementException:
                    continue

            if checkbox is None:
                # Try clicking likely container to reveal/activate
                try:
                    container = row.find_element(By.CSS_SELECTOR, 'div[data-testid="resultsPaneCell-checkbox"], [class*="checkbox"]')
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                    time.sleep(0.1)
                    self.driver.execute_script("arguments[0].click();", container)
                    time.sleep(0.1)
                    checkbox = row.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                except Exception:
                    return False

            if checkbox.is_selected():
                return True

            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
            time.sleep(0.05)
            try:
                checkbox.click()
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", checkbox)
                except Exception:
                    # React-friendly event bubbling
                    self.driver.execute_script("""
                        const cb = arguments[0];
                        cb.checked = true;
                        ['mousedown','mouseup','click','input','change'].forEach(t => {
                            cb.dispatchEvent(new Event(t, {bubbles:true}));
                        });
                    """, checkbox)

            time.sleep(0.05)
            return checkbox.is_selected()
        except Exception:
            return False

    def _wait_for_download(self, download_dir: str, timeout: int = 30) -> bool:
        """Wait for download to complete"""
        download_path = Path(download_dir)
        initial_files = set(download_path.glob('*')) if download_path.exists() else set()
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if download_path.exists():
                current_files = set(download_path.glob('*'))
                new_files = current_files - initial_files
                if new_files:
                    self.logger.info(f"✅ Download detected: {list(new_files)}")
                    return True
            time.sleep(1)
        
        self.logger.warning("⚠️ No download detected")
        return False

    def _click_export_button(self) -> bool:
        """Handle export button clicking (handles 'Export documents'/'Export original' & More-menu)."""
        time.sleep(0.8)  # allow toolbar to enable after last selection

        # Direct toolbar button
        clicked = self.driver.execute_script("""
            const labels = ['export original','export documents','export'];
            const buttons = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
            for (const btn of buttons) {
                const t = (btn.textContent || '').trim().toLowerCase();
                if (labels.some(l => t.includes(l)) && !btn.disabled) { btn.click(); return true; }
            }
            return false;
        """)
        if clicked:
            self.logger.info("✅ Export button clicked successfully!")
            return True

        # “More” -> Export
        self.logger.info("🔄 Looking for More button...")
        more = self.driver.execute_script("""
            const btn = [...document.querySelectorAll('button')]
              .find(b => (b.textContent||'').toLowerCase().includes('more') && b.offsetParent !== null);
            if (btn) { btn.click(); return true; }
            return false;
        """)
        if more:
            time.sleep(0.4)
            export_clicked = self.driver.execute_script("""
                const items = [...document.querySelectorAll('button, [role="menuitem"], [data-testid]')]
                    .filter(x => x.offsetParent !== null);
                for (const el of items) {
                    const t = (el.textContent||'').toLowerCase();
                    if (t.includes('export')) { el.click(); return true; }
                }
                return false;
            """)
            if export_clicked:
                self.logger.info("✅ Export clicked from More menu!")
                return True

        self.logger.error("❌ Failed to click export button")
        return False

    # ---------- Simple "first N" selection & export ----------

    def _row_soft_key(self, row) -> str:
        """Fallback dedupe key if the hard document id isn't present."""
        try:
            title = row.find_element(By.CSS_SELECTOR, '[data-testid="resultsPaneCell-title"]').text.strip()
        except Exception:
            title = ""
        try:
            date = row.find_element(By.CSS_SELECTOR, '[data-cy="releaseDate"]').text.strip()
        except Exception:
            date = ""
        return f"{title}||{date}".lower()

    def _select_first_n_checkboxes(self, n: int = 20) -> int:
        """
        JS-only selection to avoid stale element refs. Re-queries each time.
        Selects rows 0..n-1 by row index; tolerates gaps by advancing when needed.
        """
        selected = 0
        tries_without_progress = 0
        max_tries = 12
        # optional: skip non-doc rows if they exist (dividers/ads)
        offset = 0

        while selected < n and tries_without_progress < max_tries:
            target_index = selected + offset  # aim sequentially, but allow skipping
            # Ensure target row is rendered
            if not self._scroll_row_into_view_js(target_index):
                tries_without_progress += 1
                offset += 1
                continue

            success = self.driver.execute_script("""
                const idx = arguments[0];

                // Locate the row by index
                const rowSel = `div[data-testid="ResultsListRow"][data-cy-rowindex="${idx}"]`;
                const row = document.querySelector(rowSel);
                if (!row) return false;

                // Hover-ish: move focus to row to reveal controls, if needed
                row.dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));

                // Find a checkbox
                let checkbox =
                    row.querySelector('input[data-chmlnid="ResultListDocumentCheckbox"]') ||
                    row.querySelector('div[data-testid="resultsPaneCell-checkbox"] input[type="checkbox"]') ||
                    row.querySelector('input[type="checkbox"]');

                // If not present, try clicking a likely container to mount it
                if (!checkbox) {
                    const container = row.querySelector('div[data-testid="resultsPaneCell-checkbox"], [class*="checkbox"]');
                    if (container) container.click();
                    checkbox =
                        row.querySelector('input[data-chmlnid="ResultListDocumentCheckbox"]') ||
                        row.querySelector('div[data-testid="resultsPaneCell-checkbox"] input[type="checkbox"]') ||
                        row.querySelector('input[type="checkbox"]');
                }
                if (!checkbox) return false;

                // If already selected, count as success
                if (checkbox.checked) return true;

                // Click normally first
                try { checkbox.click(); } catch (_) {}

                // If not selected, force-assign and dispatch React-friendly events
                if (!checkbox.checked) {
                    checkbox.checked = true;
                    ['mousedown','mouseup','click','input','change'].forEach(t => {
                        checkbox.dispatchEvent(new Event(t, {bubbles:true}));
                    });
                }
                return !!checkbox.checked;
            """, target_index)

            if success:
                selected += 1
                tries_without_progress = 0
                # Let toolbar enable as selections accrue
                time.sleep(0.12)
            else:
                tries_without_progress += 1
                offset += 1  # advance past non-interactable row

        self.logger.info(f"Selected {selected} rows (requested {n})")
        return selected

    def export_first_n_in_search(self, search_id: str, n: int = 20, output_dir: str = './exports') -> bool:
        """
        Navigate to a saved search, select the first N items, click Export, and wait for the download.
        """
        try:
            self.logger.info(f"🔎 Exporting first {n} docs from search {search_id}")

            base_url = self.config.get_alphasense_config().get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            self.driver.get(search_url)

            if not self._wait_for_results(timeout=20):
                raise Exception("Results did not load")

            # Make the selections
            selected = self._select_first_n_checkboxes(n=n)
            if selected == 0:
                self.logger.error("No rows were selected — aborting export.")
                return False

            # Click export
            if not self._click_export_button():
                self.logger.error("Export button not found/click failed.")
                return False

            # Wait for the download to show up
            ok = self._wait_for_download(output_dir, timeout=90)
            if ok:
                self.logger.info("✅ Export started and file detected in downloads.")
            else:
                self.logger.warning("⚠️ Export attempted, but no download detected within timeout.")
            return ok
        except Exception as e:
            self.logger.error(f"Failed export_first_n_in_search: {e}")
            return False

    # ---------- Cache-first (two-phase) export path you already had ----------

    def collect_all_data(self, search_id: str) -> str:
        """
        Phase 1: Collect all data from the search and save to cache
        Returns cache file path
        """
        try:
            # Navigate to search
            self.logger.info(f"🔍 Collecting data for search ID: {search_id}")
            alphasense_config = self.config.get_alphasense_config()
            base_url = alphasense_config.get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            self.logger.info(f"Navigating to: {search_url}")
            self.driver.get(search_url)

            if not self._wait_for_results():
                raise Exception("Results did not load")

            # Collect all data using virtualized scrolling
            self.logger.info("📊 Starting data collection phase...")
            total_collected = self._scroll_to_load_more_rows(target_rows=200)  # Collect more rows
            
            if total_collected == 0:
                raise Exception("No data collected")
            
            # Save to cache
            cache_file = self._save_to_cache(search_id, self.collected_row_data)
            
            self.logger.info(f"✅ Data collection complete! Collected {total_collected} rows")
            return cache_file
            
        except Exception as e:
            self.logger.error(f"❌ Error during data collection: {e}")
            raise

    def _select_checkbox_for_visible_row(self, target_row_index: int) -> bool:
        """
        Select checkbox for a row that should be currently visible (row-index path).
        Kept for cache/bundle flow.
        """
        try:
            visible_rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
            target_row = None
            
            for row in visible_rows:
                row_index = row.get_attribute('data-cy-rowindex')
                if row_index and int(row_index) == target_row_index:
                    target_row = row
                    break
            
            if not target_row:
                self.logger.warning(f"❌ Row {target_row_index} not found among visible rows")
                return False

            return self._select_checkbox_in_row(target_row)
        except Exception as e:
            self.logger.error(f"Error selecting checkbox for row {target_row_index}: {e}")
            return False

    def export_from_cache(self, cache_file: str, bundle_size: int = 20, output_dir: str = './exports') -> list:
        """
        Phase 2: Export documents in bundles using cached data
        """
        try:
            # Load cached data
            cache_data = self._load_from_cache(cache_file)
            rows = cache_data['rows']
            search_id = cache_data['search_id']
            
            self.logger.info(f"🚀 Starting export phase for {len(rows)} rows in bundles of {bundle_size}")
            
            # Navigate back to search
            alphasense_config = self.config.get_alphasense_config()
            base_url = alphasense_config.get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            self.driver.get(search_url)
            
            if not self._wait_for_results():
                raise Exception("Results did not load")
            
            scrollable_container = self._get_scrollable_container()
            exported_files = []
            
            # Process in bundles
            for bundle_start in range(0, len(rows), bundle_size):
                bundle_end = min(bundle_start + bundle_size, len(rows))
                bundle_rows = rows[bundle_start:bundle_end]
                
                self.logger.info(f"📦 Processing bundle {bundle_start//bundle_size + 1}: rows {bundle_start}-{bundle_end-1}")
                
                # Reset to top of list
                self.driver.execute_script("arguments[0].scrollTop = 0;", scrollable_container)
                time.sleep(1)
                
                # Clear any existing selections
                self.driver.execute_script("""
                    const checkboxes = document.querySelectorAll('input[data-chmlnid="ResultListDocumentCheckbox"]:checked, input[type="checkbox"]:checked');
                    checkboxes.forEach(cb => { if (cb.checked) cb.click(); });
                """)
                time.sleep(1)
                
                # Select rows for this bundle
                selected_count = 0
                for row_data in bundle_rows:
                    row_index = row_data.get('row_index')
                    if not row_index:
                        continue
                    
                    try:
                        row_index_int = int(row_index)
                        self.logger.info(f"  📍 Selecting row {row_index_int}")
                        
                        # Scroll to make row visible
                        if self._scroll_to_specific_row_index(row_index_int, scrollable_container):
                            # Select the checkbox
                            if self._select_checkbox_for_visible_row(row_index_int):
                                selected_count += 1
                                self.logger.info(f"  ✅ Selected row {row_index_int} ({selected_count}/{len(bundle_rows)})")
                            else:
                                self.logger.warning(f"  ❌ Failed to select row {row_index_int}")
                        else:
                            self.logger.warning(f"  ❌ Could not scroll to row {row_index_int}")
                            
                        # Small delay between selections
                        time.sleep(0.3)
                        
                    except (ValueError, TypeError):
                        self.logger.warning(f"  ❌ Invalid row index: {row_index}")
                        continue
                
                self.logger.info(f"📊 Bundle selection complete: {selected_count}/{len(bundle_rows)} rows selected")
                
                # Export this bundle if we have selections
                if selected_count >= 1:  # Export even with 1 item
                    if self._click_export_button():
                        # Handle download
                        time.sleep(3)  # Wait for any permission dialogs
                        
                        if self._wait_for_download(output_dir, timeout=60):
                            self.logger.info(f"✅ Bundle {bundle_start//bundle_size + 1} exported successfully!")
                            exported_files.append(f"bundle_{bundle_start//bundle_size + 1}")
                        else:
                            self.logger.warning(f"⚠️ Bundle {bundle_start//bundle_size + 1} export attempted but no download detected")
                            exported_files.append(f"bundle_{bundle_start//bundle_size + 1}_partial")
                    else:
                        self.logger.error(f"❌ Failed to export bundle {bundle_start//bundle_size + 1}")
                else:
                    self.logger.error(f"❌ No rows selected for bundle {bundle_start//bundle_size + 1}")
                
                # Wait between bundles
                time.sleep(2)
            
            self.logger.info(f"🎉 Export complete! Processed {len(exported_files)} bundles")
            return exported_files
            
        except Exception as e:
            self.logger.error(f"❌ Error during export from cache: {e}")
            return []

    def export_saved_search(self, search_id: str, max_results: int = 100, output_dir: str = './exports') -> list:
        """
        Complete export process: collect data first, then export in bundles
        """
        try:
            self.logger.info(f"🚀 Starting complete export process for search {search_id}")
            
            # Phase 1: Collect all data
            self.logger.info("📊 Phase 1: Collecting all data...")
            cache_file = self.collect_all_data(search_id)
            
            # Phase 2: Export in bundles
            self.logger.info("📦 Phase 2: Exporting in bundles...")
            exported_files = self.export_from_cache(cache_file, bundle_size=20, output_dir=output_dir)
            
            if exported_files:
                self.logger.info(f"✅ Complete export successful! {len(exported_files)} bundles exported")
                return exported_files
            else:
                self.logger.error("❌ No files were exported")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Error in complete export process: {e}")
            return []

    def resume_export_from_cache(self, cache_file: str, output_dir: str = './exports') -> list:
        """
        Resume export process using existing cache file
        Useful if the export phase failed but data collection succeeded
        """
        self.logger.info(f"🔄 Resuming export from cache file: {cache_file}")
        return self.export_from_cache(cache_file, bundle_size=20, output_dir=output_dir)

    def list_cache_files(self) -> list:
        """List available cache files"""
        cache_files = list(self.cache_dir.glob('search_*.json'))
        self.logger.info(f"📁 Found {len(cache_files)} cache files:")
        for cache_file in cache_files:
            self.logger.info(f"  - {cache_file.name}")
        return [str(f) for f in cache_files]

    def debug_checkbox_structure(self, max_rows: int = 3) -> None:
        """
        Debug method to understand the checkbox structure in the current page
        """
        self.logger.info("🔍 Debugging checkbox structure...")
        
        try:
            visible_rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
            self.logger.info(f"Found {len(visible_rows)} visible rows")
            
            for i, row in enumerate(visible_rows[:max_rows]):
                row_index = row.get_attribute('data-cy-rowindex')
                self.logger.info(f"\n--- Row {i} (index: {row_index}) ---")
                
                # Check for different checkbox patterns
                checkbox_patterns = [
                    'div[data-testid="resultsPaneCell-checkbox"]',
                    'input[data-chmlnid="ResultListDocumentCheckbox"]',
                    'input[type="checkbox"]',
                    '.as-checkbox-icon',
                    '[class*="checkbox"]',
                    'label',
                ]
                
                for pattern in checkbox_patterns:
                    try:
                        elements = row.find_elements(By.CSS_SELECTOR, pattern)
                        if elements:
                            self.logger.info(f"  ✓ Found {len(elements)} elements with pattern: {pattern}")
                            for j, elem in enumerate(elements[:2]):  # Show first 2
                                self.logger.info(f"    Element {j}: {elem.tag_name}, classes: {elem.get_attribute('class')}")
                        else:
                            self.logger.info(f"  ❌ No elements found with pattern: {pattern}")
                    except Exception as e:
                        self.logger.info(f"  ❌ Error with pattern {pattern}: {e}")
                
                # Check if row is clickable
                try:
                    is_clickable = self.driver.execute_script("""
                        const row = arguments[0];
                        const rect = row.getBoundingClientRect();
                        const style = window.getComputedStyle(row);
                        
                        return {
                            hasClickListener: row.onclick !== null,
                            cursor: style.cursor,
                            pointerEvents: style.pointerEvents,
                            position: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                        };
                    """, row)
                    self.logger.info(f"  Row clickability: {is_clickable}")
                except Exception as e:
                    self.logger.info(f"  Error checking clickability: {e}")
                
                # Get a preview of the row HTML
                try:
                    row_html = row.get_attribute('outerHTML')[:300]  # First 300 chars
                    self.logger.info(f"  HTML preview: {row_html}...")
                except Exception as e:
                    self.logger.info(f"  Error getting HTML: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error in debug_checkbox_structure: {e}")

    def get_cache_info(self, cache_file: str) -> dict:
        """Get basic information about a cache file."""
        try:
            cache_data = self._load_from_cache(cache_file)
            return {
                'search_id': cache_data.get('search_id'),
                'collected_at': cache_data.get('collected_at'),
                'total_rows': cache_data.get('total_rows'),
                'first_few_titles': [
                    (row.get('title') or 'N/A') if not row.get('title') or len(row.get('title')) <= 50
                    else row.get('title')[:50] + '...'
                    for row in cache_data.get('rows', [])[:3]
                ]
            }
        except Exception as e:
            self.logger.error(f"Error reading cache file {cache_file}: {e}")
            return {}
