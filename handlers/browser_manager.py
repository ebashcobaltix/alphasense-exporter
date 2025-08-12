# browser_manager.py

from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
)
from webdriver_manager.chrome import ChromeDriverManager

from config import Config
from logger import get_logger


class BrowserManager:
    """Handles browser setup, configuration, and basic navigation"""
    
    def __init__(self, config: Config, headless: bool = True):
        self.config = config
        self.logger = get_logger(__name__)
        self.driver = None
        self.headless = headless
        self.wait = None
        self._browser_download_dir = None
        
        self._setup_browser()
    
    def _setup_browser(self) -> None:
        """Set up chrome browser with all necessary options and configurations"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        
        browser_config = self.config.get_browser_config()
        window_size = browser_config.get('window_size', {'width': 1920, 'height': 1080})
        chrome_options.add_argument(f'--window-size={window_size["width"]},{window_size["height"]}')
        
        user_agent = browser_config.get('user_agent')
        if user_agent:
            chrome_options.add_argument(f'--user-agent={user_agent}')
        
        # Performance optimizations
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')

        # Download configuration
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

        # Setup timeouts and waits
        timeout = browser_config.get('timeout', 30)
        implicit_wait = browser_config.get('implicit_wait', 10)
        self.driver.implicitly_wait(implicit_wait)
        self.wait = WebDriverWait(self.driver, timeout)

        self.logger.info(f"Browser setup completed. Download directory: {download_dir_path}")
        self._browser_download_dir = download_dir_path
    
    def get_download_dir(self) -> str:
        """Get the configured download directory"""
        return self._browser_download_dir or './exports'
    
    def navigate_to(self, url: str) -> None:
        """Navigate to a URL"""
        self.driver.get(url)
        self.logger.info(f"Navigated to: {url}")
    
    def wait_for_results(self, timeout: int = 20) -> bool:
        """Wait for search results to load on the page"""
        try:
            self.wait.until(EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]')),
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="ResultsList"]'))
            ))
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="ResultsListRow"]'))
            )
            self.logger.info("Results loaded")
            return True
        except TimeoutException:
            self.logger.error("Results did not load")
            return False
    
    def login(self, username: str, password: str) -> bool:
        """Handle login to AlphaSense"""
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
        """Check if user is successfully logged in"""
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
    
    def close(self) -> None:
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser closed")