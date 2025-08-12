# investigate_dom.py - Simple script to investigate DOM settings (fixed for Selenium 4)
import os
from scraper import AlphaSenseScraper
from config import Config
from logger import get_logger

# Selenium 4 imports
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


def _wait_for_results(driver, timeout=30):
    """Local wait helper in case AlphaSenseScraper._wait_for_results() is missing."""
    wait = WebDriverWait(driver, timeout)
    # Wait for the results container and at least one row to appear
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="ResultsList"], [role="list"]')))
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="ResultsListRow"]')))


def _investigate_display_settings_local(driver):
    """Local fallback: probe for count/sort/page-size controls and current visible rows."""
    info = {}
    try:
        el = driver.find_element(By.CSS_SELECTOR, '[data-testid="results-count"], [class*="resultsCount"], [class*="ResultsCount"]')
        info["results_count_text"] = el.text.strip()
    except Exception:
        pass

    try:
        sort = driver.find_element(By.CSS_SELECTOR, '[data-testid="sort"], [aria-label*="Sort"], [class*="Sort"]')
        info["sort_control_present"] = True
        info["sort_text"] = sort.text.strip()
    except Exception:
        info["sort_control_present"] = False

    try:
        candidates = driver.find_elements(By.XPATH, "//button[contains(., 'per page') or contains(., 'Rows') or contains(., 'Page size')]")
        if candidates:
            info["page_size_button_text"] = [c.text for c in candidates if c.text.strip()]
    except Exception:
        pass

    try:
        rows = driver.find_elements(By.CSS_SELECTOR, '[data-testid="ResultsListRow"]')
        info["visible_rows"] = len(rows)
    except Exception:
        pass

    return info


def _try_modify_page_size_local(driver, target_size=100):
    """
    Fallback strategy:
      1) If a 'per page' or 'rows' menu exists, select largest option.
      2) Otherwise, aggressively scroll to force more rows into DOM (virtualized list).
    Returns True if visible row count increases.
    """
    before = len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="ResultsListRow"]'))

    # Attempt a page-size control
    try:
        buttons = driver.find_elements(By.XPATH, "//button[contains(., 'per page') or contains(., 'Rows') or contains(., 'Page size')]")
        if buttons:
            buttons[0].click()
            time.sleep(0.5)
            # pick the biggest numeric option in the menu
            options = driver.find_elements(
                By.XPATH,
                "//button[.//text()[contains(.,'20') or contains(.,'50') or contains(.,'100') or contains(.,'200')]]"
                " | //li[.//text()[contains(.,'20') or contains(.,'50') or contains(.,'100') or contains(.,'200')]]"
            )
            numeric = []
            for o in options:
                try:
                    n = int(''.join(ch for ch in o.text if ch.isdigit()))
                    numeric.append((n, o))
                except Exception:
                    pass
            if numeric:
                _, biggest = sorted(numeric)[-1]
                biggest.click()
                time.sleep(1.0)
    except Exception:
        pass

    after_click = len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="ResultsListRow"]'))

    # If rows didn't increase, force-load by scrolling
    if after_click <= before:
        try:
            container = None
            containers = driver.find_elements(By.CSS_SELECTOR, '[data-testid="ResultsList"], [class*="results"], [role="list"]')
            if containers:
                container = containers[0]
            for _ in range(40):
                if container:
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                else:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.25)
        except Exception:
            pass

    after = len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="ResultsListRow"]'))
    return after > before


def _debug_checkbox_structure_local(driver, max_rows=3, logger=None):
    """Fallback: log any checkbox-like selectors in the first few rows."""
    rows = driver.find_elements(By.CSS_SELECTOR, '[data-testid="ResultsListRow"]')[:max_rows]
    for idx, row in enumerate(rows, 1):
        try:
            cbs = row.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"], [role="checkbox"], [data-testid*="checkbox"]')
            labels = [cb.get_attribute("aria-label") or cb.get_attribute("name") or cb.get_attribute("id") for cb in cbs]
            msg = f"[Row {idx}] checkboxes={len(cbs)} labels={labels}"
            (logger.info if logger else print)(msg)
        except Exception as e:
            (logger.error if logger else print)(f"[Row {idx}] error: {e}")


def investigate_dom():
    logger = get_logger(__name__)

    # Load configuration
    config = Config()

    # Get credentials
    username = config.get('credentials.username') or os.getenv('ALPHASENSE_USERNAME')
    password = config.get('credentials.password') or os.getenv('ALPHASENSE_PASSWORD')

    if not username or not password:
        logger.error("Missing credentials.")
        return

    # Create scraper instance (non-headless to see what's happening)
    scraper = AlphaSenseScraper(config, headless=False)

    try:
        # Login
        if not scraper.login(username, password):
            logger.error("Login failed")
            return

        search_id = "33f44ae2-0467-4f79-ab72-54e18a430ca8"

        # Navigate to search
        logger.info(f"Navigating to search: {search_id}")
        scraper.driver.get(f"https://research.alpha-sense.com/search?search_id={search_id}")

        # Wait for results (prefer scraper method; else local)
        if hasattr(scraper, "_wait_for_results"):
            scraper._wait_for_results()
        else:
            _wait_for_results(scraper.driver)

        # Check current state
        initial_rows = scraper.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
        logger.info(f"📊 Initial visible rows: {len(initial_rows)}")

        # Investigate available settings (prefer scraper method; else local)
        logger.info("🔍 Investigating display settings...")
        if hasattr(scraper, "investigate_display_settings"):
            settings_info = scraper.investigate_display_settings()
        else:
            settings_info = _investigate_display_settings_local(scraper.driver)

        if settings_info:
            logger.info("✅ Found display settings:")
            for key, value in settings_info.items():
                if isinstance(value, dict):
                    logger.info(f"\n📋 {key}:")
                    for sub_key, sub_value in value.items():
                        logger.info(f"  {sub_key}: {sub_value}")
                else:
                    logger.info(f"  {key}: {value}")
        else:
            logger.info("❌ No display settings found")

        # Try to modify page size (prefer scraper method; else local)
        logger.info("\n🔧 Attempting to modify page size...")
        if hasattr(scraper, "try_modify_page_size"):
            changed = scraper.try_modify_page_size(target_size=100)
        else:
            changed = _try_modify_page_size_local(scraper.driver, target_size=100)

        if changed:
            logger.info("✅ Page size / load modification successful!")
            new_rows = scraper.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')
            logger.info(f"📊 Rows after modification: {len(new_rows)}")
            if len(new_rows) > len(initial_rows):
                logger.info(f"🎉 SUCCESS! Increased from {len(initial_rows)} to {len(new_rows)} rows")
            else:
                logger.info("⚠️ Row count didn't increase (UI may be virtualized or capped)")
        else:
            logger.info("❌ Page size modification failed")

        # Debug checkbox structure (prefer scraper method; else local)
        logger.info("\n🧪 Debugging checkbox structure...")
        if hasattr(scraper, "debug_checkbox_structure"):
            scraper.debug_checkbox_structure(max_rows=3)
        else:
            _debug_checkbox_structure_local(scraper.driver, max_rows=3, logger=logger)

        # Keep browser open for manual inspection
        input("\nPress Enter to close browser and exit...")

    finally:
        scraper.close()


if __name__ == "__main__":
    investigate_dom()
