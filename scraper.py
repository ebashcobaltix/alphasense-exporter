# scraper.py

import time
import os
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
    """Core scraper class for AlphaSense saved search exports"""
    
    def __init__(self, config: Config, headless: bool = True):
        self.config = config
        self.logger = get_logger(__name__)
        self.driver = None
        self.headless = headless
        
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
            print(username_field)
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

    def _wait_for_results(self, timeout: int = 5) -> bool:
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[data-testid='resultsPaneCell-checkbox'] input[type='checkbox']")
            ))
            self.logger.info("✅ At least one result row loaded.")
            return True
        except TimeoutException:
            self.logger.error("❌ Timeout: No result rows loaded in time.")
            return False

    def _scroll_to_load_more_rows(self, target_rows: int = 121) -> int:
        """Scroll through virtualized list and collect data in batches"""
        selector = 'div[data-testid="ResultsListRow"]'
        
        try:
            # Find the scrollable container
            scrollable_container = self.driver.find_element(
                By.CSS_SELECTOR,
                'div[name="ResultList"] div[style*="overflow"]'
            )
            self.logger.info(f"Found scrollable container with selector: div[name=\"ResultList\"] div[style*=\"overflow\"]")
        except NoSuchElementException:
            try:
                scrollable_container = self.driver.find_element(By.CSS_SELECTOR, 'div[name="ResultList"]')
                self.logger.info(f"Found scrollable container with fallback selector: div[name=\"ResultList\"]")
            except NoSuchElementException:
                self.logger.warning("Could not find scrollable container, using body")
                scrollable_container = self.driver.find_element(By.TAG_NAME, 'body')

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
                
                # Try different loading strategies based on current strategy
                strategy = strategies[current_strategy % len(strategies)]
                
                if strategy == "keyboard_navigation":
                    # Try using keyboard navigation to trigger loading
                    try:
                        last_row = self.driver.find_elements(By.CSS_SELECTOR, selector)[-1] if self.driver.find_elements(By.CSS_SELECTOR, selector) else None
                        if last_row:
                            last_row.click()
                            time.sleep(0.2)
                            # Use arrow keys to navigate beyond visible area
                            for _ in range(10):
                                last_row.send_keys(Keys.ARROW_DOWN)
                                time.sleep(0.1)
                    except Exception:
                        pass
                
                elif strategy == "scroll_container":
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
                
                elif strategy == "click_last_row":
                    # Click on the last visible row and try to trigger more loading
                    try:
                        rows = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if rows:
                            last_row = rows[-1]
                            self.driver.execute_script("arguments[0].scrollIntoView();", last_row)
                            time.sleep(0.2)
                            last_row.click()
                            time.sleep(0.5)
                    except Exception:
                        pass
                
                elif strategy == "page_down_keys":
                    # Try page down keys multiple times
                    try:
                        for _ in range(5):
                            scrollable_container.send_keys(Keys.PAGE_DOWN)
                            time.sleep(0.2)
                        scrollable_container.send_keys(Keys.END)
                        time.sleep(0.5)
                    except Exception:
                        pass
                        
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
    
    def export_saved_search(self, search_id: str, max_results: int = 100,  output_dir: str = './exports') -> list:
        """Export a saved search in batches of 20 by visible row index, aggregate all files."""

        try:
            self.logger.info(f"Exporting saved search: (ID: {search_id})")
            alphasense_config = self.config.get_alphasense_config()
            base_url = alphasense_config.get('base_url', 'https://research.alpha-sense.com')
            search_url = f"{base_url}/search?search_id={search_id}"
            self.logger.info(f"Navigating to: {search_url}")
            self.driver.get(search_url)

            if not self._wait_for_results():
                raise Exception("Results did not load within timeout")
        
        except Exception as e:
            self.logger.error(f"Error during saved search retrieval: {e}")

        # scrolling through virtualized list and collect data progressively
        try:
            self.logger.info("Scrolling through virtualized list to collect all data...")
            total_collected = self._scroll_to_load_more_rows(target_rows=121)  
            self.logger.info(f"Successfully collected {total_collected} total rows")
            
            print(f"Collected {len(self.collected_row_data)} unique rows from virtualized list:")
            for i, row_data in enumerate(self.collected_row_data):
                print(f"Row {i}: {row_data}")
                
        except Exception as e:
            self.logger.error(f"Error during virtualized list collection: {e}")

        # smaller batch for selection (since DOM only shows ~27)
        try:
            scrollable_container = self.driver.find_element(
                By.CSS_SELECTOR,
                'div[name="ResultList"] div[style*="overflow"]'
            )
            self.driver.execute_script("arguments[0].scrollTop = 0;", scrollable_container)
            time.sleep(1)
            
        except Exception as e:
            self.logger.error(f"Error resetting scroll position: {e}")

        try:
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            row_divs = soup.find_all("div", {"data-testid": "ResultsListRow"})
            print(f"Found {len(row_divs)} rows currently visible for selection.")

            for i, row in enumerate(row_divs[:5]):  
                row_index = row.get("data-cy-rowindex")
                title = row.find(attrs={'data-testid': 'resultsPaneCell-title'})
                print(f"Visible row {i}: Index {row_index}, Title: {title.text.strip() if title else 'N/A'}")
            
        except Exception as e:
            self.logger.error(f"Error during visible rows parsing: {e}")

        max_rows = min(30, len(getattr(self, 'collected_row_data', []))) 

        try:
            selector = 'div[data-testid="ResultsListRow"]'
            block_size = 20

            time.sleep(1)
            
            row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            total_rows = len(row_elements)

            if not row_elements:
                self.logger.warning(f"No result elements found with selector: {selector}")
            else:
                self.logger.info(f"Found {total_rows} result elements with selector: {selector}")

                start_idx = 0
                while start_idx < total_rows and start_idx < max_rows:
                    end_idx = min(start_idx + block_size, total_rows, max_rows)
                    print(f"Selecting rows {start_idx} to {end_idx - 1}")
                    
                    try:
                        row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if len(row_elements) < end_idx:
                            self.logger.warning(f"Not enough rows found. Expected {end_idx}, got {len(row_elements)}")
                            break
                    except Exception as e:
                        self.logger.error(f"Error refreshing row elements: {e}")
                        break

                    try:
                        first_element = row_elements[start_idx]
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_element)
                        time.sleep(0.3)  
                        first_element.click()
                        time.sleep(0.2)
                    except StaleElementReferenceException:
                        self.logger.warning(f"Stale element at start index {start_idx}, refreshing and retrying...")
                        row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if len(row_elements) > start_idx:
                            first_element = row_elements[start_idx]
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_element)
                            time.sleep(0.3)
                            first_element.click()
                            time.sleep(0.2)
                        else:
                            self.logger.error(f"Cannot recover from stale element at index {start_idx}")
                            break

                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.SHIFT)
                    
                    for idx in range(start_idx + 1, end_idx):
                        try:
                            actions.send_keys(Keys.ARROW_DOWN)
                            actions.perform()
                            time.sleep(0.15) 
                        except StaleElementReferenceException:
                            self.logger.warning(f"Stale element during arrow key navigation at row {idx}")
                            actions = ActionChains(self.driver)
                            actions.key_down(Keys.SHIFT)
                        except Exception as e:
                            self.logger.warning(f"Error during arrow key navigation at row {idx}: {e}")
                    
                    actions.key_up(Keys.SHIFT)
                    actions.perform()
                    time.sleep(0.3) 
                    print(f"Selected block {start_idx}-{end_idx - 1}")

                    if end_idx < total_rows and end_idx < max_rows:
                        try:
                            row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            if len(row_elements) > end_idx:
                                next_element = row_elements[end_idx]
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_element)
                                time.sleep(0.3)
                                next_element.click() 
                                time.sleep(0.2)
                            else:
                                self.logger.warning(f"Cannot find next element at index {end_idx}")
                        except StaleElementReferenceException:
                            self.logger.warning(f"Stale element when moving to next block at index {end_idx}")
                    
                    start_idx = end_idx 

        except Exception as e:
            self.logger.error(f"Error during block row selection: {e}")

    def _scroll_and_click_row(self, selector, row_idx, timeout=5):
        # Wait for elements to appear
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, selector)) > row_idx
            )
        except TimeoutException:
            print(f"Row {row_idx} did not appear after {timeout}s")
            return False

        # Refetch elements and get the desired row
        row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
        if len(row_elements) <= row_idx:
            print(f"Row index {row_idx} not found in DOM.")
            return False

        el = row_elements[row_idx]
        # Scroll into view
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        # Wait for clickable
        try:
            WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            el.click()
            return True
        except TimeoutException:
            print(f"Row {row_idx} not clickable after scrolling.")
            return False