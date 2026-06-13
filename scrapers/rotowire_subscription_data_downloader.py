"""
RotoWire College Basketball Picks Scraper
Downloads Lines and Line Movements data for March Madness
Requires authentication and handles CSV downloads
"""

import os
import sys
import time
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("ERROR: selenium not installed. Run: pip install selenium")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RotoWireCBBScraper:
    """Scraper for RotoWire CBB picks data with authentication"""
    
    def __init__(self, output_dir: str = None):
        self.base_url = 'https://www.rotowire.com/picks/cbb/'
        self.login_url = 'https://www.rotowire.com/users/login.php'
        
        # Get credentials from environment
        self.username = os.getenv('ROTOWIRE_USERNAME')
        self.password = os.getenv('ROTOWIRE_PASSWORD')
        
        logger.info(f"Checking credentials...")
        logger.info(f"Username set: {bool(self.username)}")
        logger.info(f"Password set: {bool(self.password)}")
        
        if not self.username or not self.password:
            logger.error("MISSING CREDENTIALS!")
            logger.error("Set ROTOWIRE_USERNAME and ROTOWIRE_PASSWORD in .env or environment")
            raise ValueError("Missing RotoWire credentials")
        
        logger.info("Credentials verified")
        
        # Use absolute path based on project root
        if output_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.output_dir = os.path.join(project_root, 'data', 'rotowire_subscription')
        else:
            self.output_dir = output_dir
        
        self.lines_dir = os.path.join(self.output_dir, 'lines')
        self.movements_dir = os.path.join(self.output_dir, 'line_movements')
        
        # Create output directories
        os.makedirs(self.lines_dir, exist_ok=True)
        os.makedirs(self.movements_dir, exist_ok=True)
        logger.info(f"Output directories ready: {self.output_dir}")
        
        # Set up download directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.download_dir = os.path.join(project_root, 'temp_downloads')
        os.makedirs(self.download_dir, exist_ok=True)
        logger.info(f"Download directory: {self.download_dir}")
        
        self.driver = None
        
    def setup_driver(self):
        """Set up Selenium WebDriver with download preferences"""
        try:
            chrome_options = Options()
            
            # Configure download behavior
            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            # Enable headless mode for CI/CD environments
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10)
            logger.info("✓ Chrome WebDriver initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize Chrome: {e}")
            raise
        
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")
            
    def login(self) -> bool:
        """Log in to RotoWire"""
        try:
            logger.info(f"→ Navigating to login page...")
            self.driver.get(self.login_url)
            time.sleep(3)
            
            # Wait for login form to load
            wait = WebDriverWait(self.driver, 15)
            
            logger.info("→ Finding username field by placeholder...")
            # Username field has placeholder="Enter username"
            username_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Enter username"]'))
            )
            logger.info("✓ Found username field")
                
            username_field.clear()
            username_field.send_keys(self.username)
            logger.info("✓ Username entered")
            
            logger.info("→ Finding password field by placeholder...")
            # Password field has placeholder="Enter your password" and type="password"
            password_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Enter your password"][type="password"]'))
            )
            logger.info("✓ Found password field")
                
            password_field.clear()
            password_field.send_keys(self.password)
            logger.info("✓ Password entered")
            
            logger.info("→ Submitting login form...")
            # Submit using Enter key
            password_field.send_keys(Keys.RETURN)
            logger.info("✓ Submitted form")
            
            logger.info("→ Waiting for login to complete...")
            time.sleep(5)
            
            # Check if login was successful
            current_url = self.driver.current_url.lower()
            if "login" in current_url or "signin" in current_url:
                logger.error(f"✗ Login failed - still on login page: {current_url}")
                return False
            else:
                logger.info(f"✓ Login successful - redirected to: {current_url}")
                return True
                
        except Exception as e:
            logger.error(f"✗ Error during login: {e}", exc_info=True)
            return False
            
    def wait_for_download(self, timeout: int = 30) -> Optional[str]:
        """Wait for a file to appear in the download directory"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Get list of files in download directory
            files = list(Path(self.download_dir).glob('*'))
            
            # Filter out partial downloads
            complete_files = [f for f in files if not str(f).endswith('.crdownload')]
            
            if complete_files:
                # Return the most recent file
                newest_file = max(complete_files, key=lambda x: x.stat().st_mtime)
                logger.info(f"Download complete: {newest_file.name}")
                return str(newest_file)
            
            time.sleep(1)
        
        logger.error("Download timed out")
        return None
        
    def download_lines_data(self) -> bool:
        """Navigate to research page and download lines data"""
        try:
            logger.info("Navigating to CBB picks page")
            self.driver.get(self.base_url)
            time.sleep(5)
            
            # Click on Research button
            wait = WebDriverWait(self.driver, 10)
            
            try:
                # Research button: <button>...<svg>...</svg>Research</button>
                research_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Research')]"))
                )
                research_button.click()
                logger.info("✓ Clicked Research button")
                time.sleep(3)
            except Exception as e:
                logger.warning(f"Could not find Research button - may already be on research page: {e}")
            
            # Click on "Lines" button within Research tab
            try:
                # Lines button: <button class="...bg-buttons-primary-pressed...">Lines</button>
                lines_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Lines')]"))
                )
                lines_button.click()
                logger.info("✓ Clicked Lines button")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Could not find Lines button - may already be selected: {e}")
            
            # Note: Not applying "Today Only" filter - fetching all available data
            
            # Clear download directory before downloading
            self._clear_download_dir()
            
            # Wait for page to fully load
            logger.info("Waiting for page to fully load...")
            time.sleep(5)
            
            # Find CSV export button
            # Structure: <div>Export Table Data → <button class="bg-error-600">CSV</button></div>
            logger.info("Looking for CSV export button...")
            
            try:
                # Wait for the CSV button with bg-error-600 class
                download_button = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.bg-error-600"))
                )
                logger.info(f"✓ Found CSV export button")
                logger.info(f"Button text: {download_button.text}")
            except Exception as e:
                logger.error(f"✗ Could not find CSV export button: {e}")
                return False
            
            # Scroll to button and click
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
                time.sleep(1)
                download_button.click()
                logger.info("✓ Clicked CSV export button for lines data")
            except Exception as e:
                logger.error(f"Failed to click button: {e}")
                # Try JavaScript click as fallback
                try:
                    self.driver.execute_script("arguments[0].click();", download_button)
                    logger.info("✓ Clicked CSV export button using JavaScript")
                except Exception as e2:
                    logger.error(f"JavaScript click also failed: {e2}")
                    return False
            
            # Wait for download to complete
            downloaded_file = self.wait_for_download()
            
            if downloaded_file:
                # Move file to proper location
                self._save_file(downloaded_file, 'lines')
                return True
            else:
                logger.error("Failed to download lines data")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading lines data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    def download_line_movements_data(self) -> bool:
        """Download line movements data"""
        try:
            # Navigate to line movements section
            wait = WebDriverWait(self.driver, 10)
            
            try:
                # Line Movements button: <button>...<svg>...</svg>Line Movements</button>
                movements_button = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Line Movements')]"))
                )
                
                # Scroll to button and wait
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", movements_button)
                time.sleep(1)
                
                # Try regular click first
                try:
                    movements_button.click()
                    logger.info("✓ Clicked Line Movements button")
                except Exception as click_error:
                    # If regular click fails, use JavaScript click
                    logger.warning(f"Regular click failed, trying JavaScript click: {click_error}")
                    self.driver.execute_script("arguments[0].click();", movements_button)
                    logger.info("✓ Clicked Line Movements button using JavaScript")
                
                time.sleep(3)
            except Exception as e:
                logger.error(f"✗ Could not find Line Movements button: {e}")
                return False
            
            # Select "Today Only" filter if needed
            try:
                today_filter = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Today Only') or contains(@value, 'today')]")
                today_filter.click()
                logger.info("Applied 'Today Only' filter for line movements")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Could not find 'Today Only' filter for line movements: {e}")
            
            # Clear download directory before downloading
            self._clear_download_dir()
            
            # Find CSV export button for line movements
            logger.info("Looking for CSV export button for line movements...")
            
            try:
                # Wait for the CSV button with bg-error-600 class
                download_button = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.bg-error-600"))
                )
                logger.info(f"✓ Found CSV export button")
                logger.info(f"Button text: {download_button.text}")
                
                # Scroll to button and click
                self.driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
                time.sleep(1)
                download_button.click()
                logger.info("✓ Clicked CSV export button for line movements data")
            except Exception as e:
                logger.error(f"✗ Could not find or click CSV export button: {e}")
                return False
            
            # Wait for download to complete
            downloaded_file = self.wait_for_download()
            
            if downloaded_file:
                # Move file to proper location
                self._save_file(downloaded_file, 'line_movements')
                return True
            else:
                logger.error("Failed to download line movements data")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading line movements data: {e}")
            return False
            
    def _clear_download_dir(self):
        """Clear the download directory"""
        for file in Path(self.download_dir).glob('*'):
            try:
                file.unlink()
            except Exception as e:
                logger.warning(f"Could not delete {file}: {e}")
                
    def _save_file(self, source_path: str, data_type: str):
        """Save downloaded file to proper location with timestamp"""
        # Get current time in Eastern Time
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        date_str = now_et.strftime('%Y-%m-%d')
        time_str = now_et.strftime('%H%M%S')
        
        # Determine destination directory
        if data_type == 'lines':
            dest_dir = self.lines_dir
            prefix = 'rotowire_lines'
        else:
            dest_dir = self.movements_dir
            prefix = 'rotowire_movements'
        
        # Create date subdirectory
        date_dir = os.path.join(dest_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        
        # Copy file to date directory with timestamp
        filename = f"{prefix}_{date_str}_{time_str}.csv"
        dest_path = os.path.join(date_dir, filename)
        shutil.copy2(source_path, dest_path)
        logger.info(f"Saved {data_type} data to: {dest_path}")
        
    def scrape(self) -> Tuple[bool, bool]:
        """Main scraping method - returns (lines_success, movements_success)"""
        lines_success = False
        movements_success = False
        
        try:
            logger.info("Setting up Chrome driver...")
            self.setup_driver()
            
            # Log in
            logger.info("Attempting to log in...")
            if not self.login():
                logger.error("Login failed - cannot proceed with scraping")
                return (False, False)
            
            # Download lines data
            logger.info("Downloading lines data...")
            lines_success = self.download_lines_data()
            
            # Download line movements data
            logger.info("Downloading line movements data...")
            movements_success = self.download_line_movements_data()
            
            return (lines_success, movements_success)
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}", exc_info=True)
            return (False, False)
        finally:
            logger.info("Closing driver...")
            self.close_driver()
            # Clean up temp download directory
            logger.info("Cleaning up temp directory...")
            try:
                shutil.rmtree(self.download_dir)
            except Exception as e:
                logger.warning(f"Could not remove temp directory: {e}")


def main():
    """Run the scraper"""
    print("\n" + "="*80)
    logger.info("RotoWire CBB Scraper Starting")
    print("="*80 + "\n")
    
    try:
        logger.info("Initializing scraper...")
        scraper = RotoWireCBBScraper()
        
        logger.info("Starting scrape...")
        lines_success, movements_success = scraper.scrape()
        
        print("\n" + "="*80)
        if lines_success and movements_success:
            logger.info("✓ SUCCESS: Both datasets downloaded")
            print("="*80)
            return 0
        elif lines_success or movements_success:
            logger.warning("⚠ PARTIAL: Only one dataset downloaded")
            print("="*80)
            return 0
        else:
            logger.error("✗ FAILED: No data downloaded")
            print("="*80)
            return 1
            
    except ValueError as e:
        logger.error(f"✗ CONFIG ERROR: {e}")
        return 2
    except Exception as e:
        logger.error(f"✗ UNEXPECTED ERROR: {e}", exc_info=True)
        return 3


if __name__ == '__main__':
    sys.exit(main())
