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


        try:

            # Parse and print all rows in the DOM before any selection occurs
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            row_divs = soup.find_all("div", {"data-testid": "ResultsListRow"})
            print(f"Found {len(row_divs)} rows currently rendered.")

            for row in row_divs:
                row_index = row.get("data-cy-rowindex")
                doc_div = row.find("div", {"data-cy-document-id": True})
                document_id = doc_div["data-cy-document-id"] if doc_div else None

                source = row.find(attrs={'data-testid': 'resultsPaneCell-source'})
                author = row.find(attrs={'data-testid': 'resultsPaneCell-author'})
                page_count = row.find(attrs={'data-testid': 'resultsPaneCell-pageCount'})
                score = row.find(attrs={'data-cy': 'score'})
                release_date = row.find(attrs={'data-cy': 'releaseDate'})
                title = row.find(attrs={'data-testid': 'resultsPaneCell-title'})
                ticker = row.find(attrs={'data-testid': 'resultsPaneCell-ticker'})
                company = row.find(attrs={'data-testid': 'resultsPaneCell-company'})

                checkbox = row.find("input", {"type": "checkbox"})
                selected = checkbox is not None and checkbox.has_attr("checked")

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
                    'selected': selected,
                }
                print(row_data)
            
        except Exception as e:
            self.logger.error(f"Error during HTML parsing: {e}")



            # # Target the parent scrollable container by class name
            # results_container = self.driver.find_element(By.CSS_SELECTOR, 'div[name="ResultList"]')
            # # Find the inner div with overflow scroll/auto
            # scrollable_container = self.driver.find_element(
            #     By.CSS_SELECTOR,
            #     'div[name="ResultList"] div[style*="overflow: auto scroll"]'
            # )
            # last_count = 0

        max_rows = 20  # Or whatever number you want

        try:
            selector = 'div[data-testid="ResultsListRow"]'
            # You can set max_rows to the total number of rows you expect, or dynamically calculate
            max_rows = 1000  # Set this as needed, or dynamically
            block_size = 20

            row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            total_rows = len(row_elements)

            if not row_elements:
                self.logger.warning(f"No result elements found with selector: {selector}")
            else:
                self.logger.info(f"Found {total_rows} result elements with selector: {selector}")

                # We'll keep track of which row to start on
                start_idx = 0
                while start_idx < total_rows:
                    # Clamp the end index to not go out of range
                    end_idx = min(start_idx + block_size, total_rows)
                    print(f"Selecting rows {start_idx} to {end_idx - 1}")
                    
                    # Refresh the row elements each time in case of DOM updates (especially important for virtualized lists!)
                    row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)

                    # Click the starting row for this block
                    first_element = row_elements[start_idx]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_element)
                    first_element.click()
                    time.sleep(0.2)

                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.SHIFT)
                    for idx in range(start_idx + 1, end_idx):
                        try:
                            actions.send_keys(Keys.ARROW_DOWN)
                            actions.perform()
                            time.sleep(0.12)
                        except StaleElementReferenceException:
                            print(f"Stale element at row {idx}, retrying...")
                            row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            if row_elements and len(row_elements) > idx:
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row_elements[idx])
                                row_elements[idx].click()
                            else:
                                print("Could not recover from stale element.")
                    actions.key_up(Keys.SHIFT)
                    actions.perform()
                    print(f"Selected block {start_idx}-{end_idx - 1}")

                    # Now, deselect and move to next block, unless we're done
                    if end_idx < total_rows:
                        next_element = row_elements[end_idx]
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_element)
                        next_element.click()  # Click to start next selection
                        time.sleep(0.2)
                    start_idx = end_idx  # Move to the next block

        except Exception as e:
            self.logger.error(f"Error during block row selection: {e}")



       
    

    def _wait_for_results(self, timeout: int = 5) -> bool:
        """
        Wait for at least one result row (checkbox) to be visible, not the whole list.
        """
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[data-testid='resultsPaneCell-checkbox'] input[type='checkbox']")
            ))
            self.logger.info("✅ At least one result row loaded.")
            return True
        except TimeoutException:
            self.logger.error("❌ Timeout: No result rows loaded in time.")
            return False
        except Exception as e:
            self.logger.error(f"Error in _wait_for_results: {e}")
            return False

    

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
