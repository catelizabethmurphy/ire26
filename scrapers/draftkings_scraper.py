"""
DraftKings NCAA Basketball Player Props Scraper
Scrapes player props data from DraftKings Sportsbook
"""

import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DraftKingsScraper:
    """Scraper for DraftKings NCAA Basketball player props"""
    
    def __init__(self, output_dir: str = None):
        # NCAA Basketball event group ID is 92483
        # tb_view=2 for Most Bet Player Props, not sorted
        self.url = 'https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/?tb_view=2&tb_eg=92483&tb_edate=n7days'
        
        # Use absolute path based on project root
        if output_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.output_dir = os.path.join(project_root, 'data', 'draftkings_props')
        else:
            self.output_dir = output_dir
        
        self.driver = None
        os.makedirs(self.output_dir, exist_ok=True)
        
    def setup_driver(self):
        """Set up Selenium WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome WebDriver initialized")
        
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")
            
    def select_most_bet_props(self):
        """Select 'Most Bet Player Props' from dropdown and set to not sorted"""
        try:
            logger.info("Looking for view dropdown menu...")
            wait = WebDriverWait(self.driver, 15)
            
            # Try to find and click dropdown - common selectors for dropdowns
            dropdown_selectors = [
                "select[name*='view']",
                "select[id*='view']",
                "select.view-select",
                "#tb_view",
                "select",
                "[role='combobox']",
                ".dropdown-toggle"
            ]
            
            for selector in dropdown_selectors:
                try:
                    dropdown = self.driver.find_element(By.CSS_SELECTOR, selector)
                    logger.info(f"Found dropdown with selector: {selector}")
                    
                    # If it's a select element, use Select
                    if dropdown.tag_name == 'select':
                        from selenium.webdriver.support.select import Select
                        select = Select(dropdown)
                        
                        # Try to select "Most Bet Player Props" by visible text or value
                        try:
                            select.select_by_visible_text("Most Bet Player Props")
                            logger.info("Selected 'Most Bet Player Props' from dropdown")
                        except:
                            try:
                                select.select_by_value("2")
                                logger.info("Selected view option by value '2'")
                            except:
                                logger.warning("Could not select specific option, using default")
                        
                        time.sleep(3)
                        break
                    else:
                        # Try clicking if it's a button/div dropdown
                        dropdown.click()
                        time.sleep(1)
                        
                        # Look for "Most Bet" option
                        options = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Most Bet')]")
                        if options:
                            options[0].click()
                            logger.info("Clicked 'Most Bet' option")
                            time.sleep(3)
                            break
                            
                except Exception as e:
                    continue
            
            # Look for sorting dropdown if exists
            try:
                sort_selectors = [
                    "select[name*='sort']",
                    "select[id*='sort']",
                    ".sort-select"
                ]
                
                for selector in sort_selectors:
                    try:
                        sort_dropdown = self.driver.find_element(By.CSS_SELECTOR, selector)
                        from selenium.webdriver.support.select import Select
                        select = Select(sort_dropdown)
                        
                        # Try to select "not sorted" or similar
                        for option in select.options:
                            if 'not' in option.text.lower() or 'none' in option.text.lower():
                                select.select_by_visible_text(option.text)
                                logger.info(f"Selected sort option: {option.text}")
                                time.sleep(2)
                                break
                        break
                    except:
                        continue
            except Exception as e:
                logger.info("No sorting dropdown found or couldn't interact with it")
                
        except Exception as e:
            logger.warning(f"Could not interact with dropdown menus: {e}")
            logger.info("Continuing with default view...")
    
    def extract_props_data(self) -> List[Dict]:
        """Extract player props data from the page"""
        props_data = []
        
        try:
            # Wait for the page to be interactive
            logger.info("Waiting for page to be ready...")
            wait = WebDriverWait(self.driver, 20)
            time.sleep(3)
            
            # Try to select Most Bet Player Props view
            self.select_most_bet_props()
            
            # Wait for the table to load
            logger.info("Waiting for player props table to load...")
            
            # Wait for table rows to appear
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr, .player-prop-row, [data-test='player-prop'], tr[class*='prop']")))
            time.sleep(5)  # Additional wait for dynamic content
            
            # Try to find the table structure
            # DraftKings tables can have different structures, so we'll try multiple selectors
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            
            if not rows:
                # Try alternative selectors
                rows = self.driver.find_elements(By.CSS_SELECTOR, "[data-test='player-prop-row'], .player-prop-row")
            
            if not rows:
                # Try finding any table rows
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[role='row']")
            
            logger.info(f"Found {len(rows)} rows")
            
            # Get Eastern Time
            est = timezone(timedelta(hours=-5))
            now_et = datetime.now(est)
            
            for idx, row in enumerate(rows):
                try:
                    # Extract text from the row
                    row_text = row.text.strip()
                    
                    if not row_text or len(row_text) < 5:
                        continue
                    
                    # Get all cells in the row
                    cells = row.find_elements(By.CSS_SELECTOR, "td, th")
                    
                    if len(cells) < 3:  # Need at least some data
                        continue
                    
                    # Extract raw data from cells
                    cell_texts = [cell.text.strip() for cell in cells]
                    
                    # Create simple record with only raw data
                    record = {
                        'scrape_date': now_et.strftime('%Y-%m-%d'),
                        'scrape_time': now_et.strftime('%H:%M:%S'),
                        'raw_data': ' | '.join(cell_texts)
                    }
                    
                    props_data.append(record)
                    
                except Exception as e:
                    logger.warning(f"Error processing row {idx}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting props data: {e}")
            # Save screenshot for debugging
            est = timezone(timedelta(hours=-5))
            now_et = datetime.now(est)
            screenshot_path = os.path.join(self.output_dir, f'error_screenshot_{now_et.strftime("%Y%m%d_%H%M%S")}.png')
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot saved to {screenshot_path}")
            
        return props_data
    
    def scrape(self) -> List[Dict]:
        """Main scraping method"""
        try:
            self.setup_driver()
            
            logger.info(f"Loading URL: {self.url}")
            self.driver.get(self.url)
            
            # Wait for page to load
            logger.info("Waiting for page to load...")
            time.sleep(10)
            
            # Save page source for debugging
            est = timezone(timedelta(hours=-5))
            now_et = datetime.now(est)
            page_source_path = os.path.join(self.output_dir, f'page_source_{now_et.strftime("%Y%m%d_%H%M%S")}.html')
            with open(page_source_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"Page source saved to {page_source_path}")
            
            # Extract data
            props_data = self.extract_props_data()
            
            logger.info(f"Extracted {len(props_data)} player prop records")
            
            return props_data
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []
            
        finally:
            self.close_driver()
    
    def save_data(self, data: List[Dict]):
        """Save data to CSV and JSON files"""
        if not data:
            logger.warning("No data to save")
            return
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Get Eastern Time
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        
        # Create timestamp for filenames
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        date_str = now_et.strftime('%Y-%m-%d')
        
        # Create top_50 folder with date subfolder
        date_dir = os.path.join(self.output_dir, 'top_50', date_str)
        os.makedirs(date_dir, exist_ok=True)
        
        # Save CSV
        csv_path = os.path.join(date_dir, f'draftkings_props_{timestamp}.csv')
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved CSV to {csv_path}")
        
        # Save JSON
        json_path = os.path.join(date_dir, f'draftkings_props_{timestamp}.json')
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved JSON to {json_path}")


def main():
    """Main execution function"""
    logger.info("="*80)
    logger.info("Starting DraftKings NCAA Basketball Props Scraper")
    logger.info("="*80)
    
    scraper = DraftKingsScraper()
    data = scraper.scrape()
    
    if data:
        scraper.save_data(data)
        logger.info(f"Successfully scraped {len(data)} records")
    else:
        logger.warning("No data was scraped")
    
    logger.info("="*80)
    logger.info("DraftKings scraper completed")
    logger.info("="*80)


if __name__ == '__main__':
    main()
