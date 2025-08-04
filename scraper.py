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
    """Enhanced scraper class for AlphaSense saved search exports with lazy loading support"""
    
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

    def _wait_for_results(self, timeout: int = 10) -> bool:
        """Wait for at least one result row to be visible"""
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[data-testid='ResultsListRow']")
            ))
            self.logger.info("✅ At least one result row loaded.")
            return True
        except TimeoutException:
            self.logger.error("❌ Timeout: No result rows loaded in time.")
            return False

    def _get_total_results_count(self) -> int:
        """Try to get the total number of results from the UI"""
        try:
            # Look for common patterns where total count is displayed
            count_selectors = [
                "[data-testid*='total']",
                "[data-testid*='count']",
                ".results-count",
                ".total-results",
                "[class*='total']",
                "[class*='count']"
            ]
            
            for selector in count_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        # Look for numbers in the text
                        import re
                        numbers = re.findall(r'\d+', text)
                        if numbers:
                            # Take the largest number found (likely the total)
                            total = max(int(n) for n in numbers)
                            if total > 0:
                                self.logger.info(f"Found total results count: {total}")
                                return total
                except:
                    continue
            
            self.logger.warning("Could not find total results count in UI")
            return 1000  # Default fallback
        except Exception as e:
            self.logger.warning(f"Error getting total results count: {e}")
            return 1000  # Default fallback

    def _scroll_to_load_all_results(self, max_expected: int = 100) -> int:
        """Scroll until no new rows load or until we hit max_expected."""
        self.logger.info(f"Scrolling to load up to {max_expected} results…")
        last_count = 0
        same_count_rounds = 0

        for _ in range(10):  # up to 10 scroll passes
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
            current_count = len(rows)

            if current_count == last_count:
                same_count_rounds += 1
            else:
                same_count_rounds = 0

            self.logger.info(f"→ loaded {current_count} rows")
            if current_count >= max_expected or same_count_rounds >= 3:
                break

            last_count = current_count

        return current_count


    def _scroll_window_to_load_more(self, expected_total: int = None) -> int:
        """Fallback method using window scrolling"""
        try:
            self.logger.info("Using window scrolling as fallback")
            current_rows = len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
            
            max_attempts = 30
            attempts = 0
            last_row_count = current_rows
            
            while attempts < max_attempts:
                attempts += 1
                
                # Scroll window to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # Try additional techniques
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.END)
                time.sleep(1)
                
                new_row_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
                
                if new_row_count > last_row_count:
                    self.logger.info(f"Window scroll progress: {new_row_count} rows")
                    last_row_count = new_row_count
                    
                    if expected_total and new_row_count >= expected_total:
                        break
                elif attempts > 10:  # Give up if no progress after many attempts
                    break
                    
            return new_row_count
            
        except Exception as e:
            self.logger.error(f"Error during window scrolling: {e}")
            return len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))

    def _select_rows_in_batches(self, total_rows: int, batch_size: int = 20) -> bool:
        """Select rows in batches, handling lazy loading"""
        try:
            selector = 'div[data-testid="ResultsListRow"]'
            
            for batch_start in range(0, total_rows, batch_size):
                batch_end = min(batch_start + batch_size, total_rows)
                self.logger.info(f"Selecting batch: rows {batch_start} to {batch_end-1}")
                
                # Ensure the target range is loaded
                if batch_end > len(self.driver.find_elements(By.CSS_SELECTOR, selector)):
                    self._scroll_to_load_more_results(target_position=batch_end)
                
                # Get fresh elements (important for lazy-loaded content)
                row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                if len(row_elements) < batch_end:
                    self.logger.warning(f"Only {len(row_elements)} rows available, expected at least {batch_end}")
                    batch_end = len(row_elements)
                
                if batch_start >= len(row_elements):
                    self.logger.warning(f"Batch start {batch_start} exceeds available rows {len(row_elements)}")
                    break
                
                # Select the batch
                try:
                    # Click first row in batch
                    first_row = row_elements[batch_start]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_row)
                    time.sleep(0.3)
                    first_row.click()
                    
                    # Shift-click to select range
                    if batch_end - batch_start > 1:
                        actions = ActionChains(self.driver)
                        actions.key_down(Keys.SHIFT)
                        
                        last_row = row_elements[batch_end - 1]
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", last_row)
                        time.sleep(0.3)
                        last_row.click()
                        
                        actions.key_up(Keys.SHIFT)
                        actions.perform()
                    
                    self.logger.info(f"✅ Selected batch {batch_start}-{batch_end-1}")
                    
                    # Optional: trigger export for this batch here if needed
                    # self._export_selected_batch(batch_start, batch_end)
                    
                except StaleElementReferenceException:
                    self.logger.warning(f"Stale element in batch {batch_start}-{batch_end-1}, retrying...")
                    time.sleep(1)
                    continue
                except Exception as e:
                    self.logger.error(f"Error selecting batch {batch_start}-{batch_end-1}: {e}")
                    continue
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error in batch selection: {e}")
            return False

    def export_saved_search(self, search_id: str, max_results: int = None, output_dir: str = './exports') -> list:
        """Export a saved search handling lazy loading properly"""
        
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
            return []

        try:
            # Get the total number of results
            total_count = self._get_total_results_count()
            if max_results:
                total_count = min(total_count, max_results)
            
            self.logger.info(f"Target results to process: {total_count}")
            
            # Load all results by scrolling
            loaded_rows = self._scroll_to_load_all_results(max_expected=total_count)

            self.logger.info(f"Loaded {loaded_rows} rows via scrolling")
            
            # If we didn't get enough results, try alternative loading strategies
            if loaded_rows < total_count * 0.8:  # Less than 80% of expected
                self.logger.warning(f"Only loaded {loaded_rows}/{total_count} rows, trying alternative strategies...")
                
                # Strategy 1: Try interacting with pagination or "load more" buttons
                self._try_load_more_buttons()
                
                # Strategy 2: Try rapid scrolling with key presses
                self._try_rapid_scroll_loading(total_count)
                
                # Get final count
                loaded_rows = len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
                self.logger.info(f"After alternative strategies: {loaded_rows} rows")
            
            # Parse all currently loaded data
            all_row_data = self._parse_all_loaded_rows()
            
            # Select rows in batches for export
            if loaded_rows > 0:
                success = self._select_rows_in_batches(min(loaded_rows, total_count))
                if success:
                    self.logger.info("✅ All batches selected successfully")
                else:
                    self.logger.warning("⚠️  Some batches may have failed")
            
            return all_row_data
            
        except Exception as e:
            self.logger.error(f"Error during export process: {e}")
            return []

    def _try_load_more_buttons(self) -> bool:
        """Try to find and click 'Load More' or pagination buttons"""
        try:
            load_more_selectors = [
                "button[data-testid*='load']",
                "button[data-testid*='more']", 
                "button[data-testid*='next']",
                "button[class*='load']",
                "button[class*='more']",
                ".load-more",
                ".show-more",
                "[data-cy*='load']",
                "[data-cy*='more']"
            ]
            
            for selector in load_more_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            text = button.text.lower()
                            if any(keyword in text for keyword in ['load', 'more', 'show', 'next']):
                                self.logger.info(f"Clicking load more button: {text}")
                                button.click()
                                time.sleep(3)
                                return True
                except:
                    continue
            
            return False
        except Exception as e:
            self.logger.warning(f"Error trying load more buttons: {e}")
            return False

    def _try_rapid_scroll_loading(self, expected_total: int) -> int:
        """Try rapid scrolling with different techniques"""
        try:
            initial_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
            
            # Strategy 1: Rapid END key presses
            body = self.driver.find_element(By.TAG_NAME, 'body')
            for i in range(20):
                body.send_keys(Keys.END)
                time.sleep(0.5)
                body.send_keys(Keys.PAGE_DOWN)
                time.sleep(0.3)
                
                current_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
                if current_count >= expected_total * 0.9:  # 90% of expected
                    break
                    
            # Strategy 2: JavaScript-based aggressive scrolling
            self.driver.execute_script("""
                function scrollToLoadAll() {
                    let lastHeight = 0;
                    let attempts = 0;
                    const maxAttempts = 30;
                    
                    function scroll() {
                        window.scrollTo(0, document.body.scrollHeight);
                        
                        // Also try scrolling specific containers
                        const containers = document.querySelectorAll('div[name="ResultList"], div[class*="scroll"], div[style*="overflow"]');
                        containers.forEach(container => {
                            if (container.scrollHeight > container.clientHeight) {
                                container.scrollTop = container.scrollHeight;
                            }
                        });
                        
                        setTimeout(() => {
                            const currentHeight = Math.max(document.body.scrollHeight, 
                                ...Array.from(containers).map(c => c.scrollHeight));
                            
                            if (currentHeight > lastHeight && attempts < maxAttempts) {
                                lastHeight = currentHeight;
                                attempts++;
                                scroll();
                            }
                        }, 1000);
                    }
                    
                    scroll();
                }
                
                scrollToLoadAll();
            """)
            
            # Wait for the JavaScript to complete
            time.sleep(15)
            
            final_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
            self.logger.info(f"Rapid scroll loading: {initial_count} -> {final_count} rows")
            
            return final_count
            
        except Exception as e:
            self.logger.error(f"Error in rapid scroll loading: {e}")
            return len(self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))

    def _parse_all_loaded_rows(self) -> list:
        """Parse all currently loaded rows in the DOM"""
        try:
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            
            row_divs = soup.find_all("div", {"data-testid": "ResultsListRow"})
            self.logger.info(f"Found {len(row_divs)} rows in DOM")
            
            all_rows = []
            
            for i, row in enumerate(row_divs):
                try:
                    row_index = row.get("data-cy-rowindex")
                    doc_div = row.find("div", {"data-cy-document-id": True})
                    document_id = doc_div["data-cy-document-id"] if doc_div else None

                    # Extract all the row data
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
                        'dom_position': i,  # Position in DOM
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
                    
                    all_rows.append(row_data)
                    
                except Exception as e:
                    self.logger.warning(f"Error parsing row {i}: {e}")
                    continue
            
            self.logger.info(f"Successfully parsed {len(all_rows)} rows")
            return all_rows
            
        except Exception as e:
            self.logger.error(f"Error during HTML parsing: {e}")
            return []

    def _scroll_and_click_row(self, selector, row_idx, timeout=5):
        """Scroll to and click a specific row by index"""
        try:
            # Wait for elements to appear
            WebDriverWait(self.driver, timeout).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, selector)) > row_idx
            )
        except TimeoutException:
            self.logger.warning(f"Row {row_idx} did not appear after {timeout}s")
            return False

        # Refetch elements and get the desired row
        row_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
        if len(row_elements) <= row_idx:
            self.logger.warning(f"Row index {row_idx} not found in DOM.")
            return False

        el = row_elements[row_idx]
        # Scroll into view
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)
        
        # Wait for clickable and click
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            el.click()
            return True
        except TimeoutException:
            self.logger.warning(f"Row {row_idx} not clickable after scrolling.")
            return False