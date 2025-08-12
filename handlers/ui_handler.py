# ui_handler.py

import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup

from logger import get_logger


class UIHandler:
    """Handles UI interactions like scrolling, checkbox selection, and button clicks"""
    
    def __init__(self, browser_manager):
        self.browser = browser_manager
        self.driver = browser_manager.driver
        self.logger = get_logger(__name__)
    
    def get_scrollable_container(self):
        """Find the main scrollable container on the page that contains results"""
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
    
    def scroll_row_into_view_js(self, row_index: int) -> bool:
        """Scroll to bring a specific row into view using JavaScript"""
        for _ in range(18): 
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
    
    def scroll_to_specific_row_index(self, row_index: int, scrollable_container) -> bool:
        """Scroll to bring a specific row index into view"""
        try:
            for _ in range(10):
                found = self.driver.execute_script("""
                    const idx = arguments[0];
                    const container = arguments[1];
                    const sel = `div[data-testid="ResultsListRow"][data-cy-rowindex="${idx}"]`;
                    const row = document.querySelector(sel);
                    if (row) {
                        row.scrollIntoView({block: 'center'});
                        return true;
                    }
                    if (container) {
                        container.scrollTop += container.clientHeight * 0.8;
                    } else {
                        window.scrollBy(0, 800);
                    }
                    return false;
                """, row_index, scrollable_container)
                
                if found:
                    return True
                time.sleep(0.3)
            
            return False
        except Exception as e:
            self.logger.error(f"Error scrolling to row {row_index}: {e}")
            return False
    
    def click_export_button(self) -> bool:
        """Find and click the export button on the page"""
        time.sleep(0.2)  # Wait for UI to settle

        # Try multiple times with short delays to find export button
        for attempt in range(5):
            clicked = self.driver.execute_script("""
                const labels = ['export original','export documents','export'];
                const buttons = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
                for (const btn of buttons) {
                    const t = (btn.textContent || '').trim().toLowerCase();
                    if (labels.some(l => t.includes(l)) && !btn.disabled) { 
                        btn.click(); 
                        return true; 
                    }
                }
                return false;
            """)
            if clicked:
                self.logger.info("Export button clicked successfully!")
                return True
            
            if attempt < 4:
                time.sleep(0.3)

        self.logger.error("Failed to click export button")
        return False
    
    def select_first_n_checkboxes(self, n: int = 20) -> int:
        """Select checkboxes for the first n rows in the results"""
        selected = 0
        tries_without_progress = 0
        max_tries = 3
        offset = 0

        # Try to detect total results
        try:
            total_results = self.driver.execute_script("""
                const sel = [
                '[data-testid="results-count"]',
                '[data-testid="search-results-count"]',
                '[data-cy="results-count"]',
                '[data-testid="ResultsCount"]',
                '[data-test="results-count"]'
                ];
                for (const s of sel) {
                    const el = document.querySelector(s);
                    if (el) {
                        const num = parseInt((el.textContent || '').replace(/[^0-9]/g, ''), 10);
                        if (!Number.isNaN(num)) return num;
                    }
                }
                return null;
            """)
        except Exception:
            total_results = None

        n_requested = n
        if isinstance(total_results, int) and total_results >= 0:
            if total_results == 0:
                self.logger.info("No results available to select.")
                return 0
            if total_results < n:
                self.logger.info(f"Only {total_results} results available; capping selection from {n} → {total_results}.")
                n = total_results

        end_reached_streak = 0
        end_streak_threshold = 3
        highest_seen_index = -1

        while selected < n and tries_without_progress < max_tries:
            target_index = selected + offset

            # Track highest visible row index
            try:
                highest_seen_index = self.driver.execute_script("""
                    const rows = Array.from(document.querySelectorAll('div[data-testid="ResultsListRow"][data-cy-rowindex]'));
                    const vals = rows
                    .map(r => parseInt(r.getAttribute('data-cy-rowindex'), 10))
                    .filter(v => !Number.isNaN(v));
                    return vals.length ? Math.max(...vals) : -1;
                """)
            except Exception:
                pass

            scrolled = self.scroll_row_into_view_js(target_index)
            if not scrolled:
                tries_without_progress += 1
                offset += 1

                if target_index > highest_seen_index:
                    end_reached_streak += 1
                    if end_reached_streak >= end_streak_threshold:
                        self.logger.info(
                            f"Reached end of list at index ~{highest_seen_index}. "
                            f"Selected {selected} (requested {n_requested})."
                        )
                        break
                else:
                    end_reached_streak = 0
                continue
            else:
                end_reached_streak = 0

            # Select checkbox via JS
            success = self.driver.execute_script("""
                const idx = arguments[0];
                const rowSel = `div[data-testid="ResultsListRow"][data-cy-rowindex="${idx}"]`;
                const row = document.querySelector(rowSel);
                if (!row) return false;

                row.dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));

                let checkbox =
                    row.querySelector('input[data-chmlnid="ResultListDocumentCheckbox"]') ||
                    row.querySelector('div[data-testid="resultsPaneCell-checkbox"] input[type="checkbox"]') ||
                    row.querySelector('input[type="checkbox"]');

                if (!checkbox) {
                    const container = row.querySelector('div[data-testid="resultsPaneCell-checkbox"], [class*="checkbox"]');
                    if (container) container.click();
                    checkbox =
                        row.querySelector('input[data-chmlnid="ResultListDocumentCheckbox"]') ||
                        row.querySelector('div[data-testid="resultsPaneCell-checkbox"] input[type="checkbox"]') ||
                        row.querySelector('input[type="checkbox"]');
                }
                if (!checkbox) return false;

                if (checkbox.checked) return true;

                try { checkbox.click(); } catch (_) {}

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
                time.sleep(0.05)
            else:
                tries_without_progress += 1
                offset += 1

        if selected < n_requested and total_results is None:
            self.logger.info(f"Selected {selected} row(s), fewer than requested ({n_requested}). Likely reached the end.")
        elif selected < n_requested and isinstance(total_results, int):
            self.logger.info(f"Selected {selected} row(s) out of {total_results} available (requested {n_requested}).")

        self.logger.info(f"Selected {selected} rows (requested {n_requested})")
        return selected
    
    def select_checkbox_for_visible_row(self, target_row_index: int) -> bool:
        """Select checkbox for a specific row that's currently visible"""
        try:
            visible_rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
            target_row = None
            
            for row in visible_rows:
                row_index = row.get_attribute('data-cy-rowindex')
                if row_index and int(row_index) == target_row_index:
                    target_row = row
                    break
            
            if not target_row:
                self.logger.warning(f"Row {target_row_index} not found among visible rows")
                return False

            return self._select_checkbox_in_row(target_row)
        except Exception as e:
            self.logger.error(f"Error selecting checkbox for row {target_row_index}: {e}")
            return False
    
    def _select_checkbox_in_row(self, row) -> bool:
        """Select the checkbox for a specific result row"""
        try:
            # Find checkbox using different selectors
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

            # If no checkbox, try clicking container to reveal it
            if checkbox is None:
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
                    # Force selection with JS
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
    
    def clear_all_checkboxes(self) -> None:
        """Clear all selected checkboxes on the page"""
        self.driver.execute_script("""
            const checkboxes = document.querySelectorAll('input[data-chmlnid="ResultListDocumentCheckbox"]:checked, input[type="checkbox"]:checked');
            checkboxes.forEach(cb => { if (cb.checked) cb.click(); });
        """)
        time.sleep(1)
    
    def debug_checkbox_structure(self, max_rows: int = 3) -> None:
        """Debug method to examine checkbox structure on the page"""
        self.logger.info("Debugging checkbox structure...")
        
        try:
            visible_rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
            self.logger.info(f"Found {len(visible_rows)} visible rows")
            
            for i, row in enumerate(visible_rows[:max_rows]):
                row_index = row.get_attribute('data-cy-rowindex')
                self.logger.info(f"\n--- Row {i} (index: {row_index}) ---")
                
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
                            self.logger.info(f"Found {len(elements)} elements with pattern: {pattern}")
                            for j, elem in enumerate(elements[:2]):  
                                self.logger.info(f"    Element {j}: {elem.tag_name}, classes: {elem.get_attribute('class')}")
                        else:
                            self.logger.info(f" No elements found with pattern: {pattern}")
                    except Exception as e:
                        self.logger.info(f"Error with pattern {pattern}: {e}")
                
                try:
                    row_html = row.get_attribute('outerHTML')[:300] 
                    self.logger.info(f"  HTML preview: {row_html}...")
                except Exception as e:
                    self.logger.info(f"  Error getting HTML: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error in debug_checkbox_structure: {e}")