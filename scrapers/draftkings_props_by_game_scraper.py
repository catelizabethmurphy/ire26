"""
DraftKings NCAA Basketball Player Props Scraper (By Game View)
Scrapes player props data from DraftKings Sportsbook - tb_view=1 (organized by game)
"""

import os
import time
import json
import logging
import traceback
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
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Set selenium and urllib3 to WARNING to reduce noise
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


class DraftKingsGameViewScraper:
    """Scraper for DraftKings NCAA Basketball player props organized by game"""
    
    def __init__(self, output_dir: str = None):
        # NCAA Basketball event group ID is 92483
        # tb_view=1 for props organized by game
        # tb_edate=today for today's games
        self.url = 'https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/?tb_view=1&tb_eg=92483&tb_edate=n7days'
        
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
    
    def extract_props_data(self) -> List[Dict]:
        """Extract player props data from the page organized by game"""
        props_data = []
        
        try:
            # Wait for the page to be interactive
            logger.info("Waiting for page to be ready...")
            wait = WebDriverWait(self.driver, 30)
            time.sleep(8)  # Give more time for JavaScript to render
            
            # Get Eastern Time
            est = timezone(timedelta(hours=-5))
            now_et = datetime.now(est)
            
            # Scroll to load all content
            logger.info("Scrolling to load all content...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            
            # Parse the page structure: h5 -> game time -> h6 (prop type) -> props
            current_matchup = None
            current_game_time = None
            current_prop_type = None
            
            # Track seen player-prop combinations to keep one record per player per prop type
            seen_player_props = set()
            
            # Get all elements in order
            all_elements = self.driver.find_elements(By.XPATH, "//*[self::h5 or self::h6 or self::a[contains(@href, 'sportsbook.draftkings.com')]]")
            
            logger.info(f"Processing {len(all_elements)} elements...")
            
            # Define prop keywords for parsing (order matters - check longer matches first!)
            prop_keywords = ['First Points Scorer', 'Points + Rebounds + Assists', 'Points + Rebounds', 
                           'Points + Assists', 'Rebounds + Assists', 'Three Pointers Made',
                           'Points', 'Rebounds', 'Assists']
            
            for elem in all_elements:
                try:
                    tag_name = elem.tag_name.lower()
                    elem_text = elem.text.strip()
                    
                    if tag_name == 'h5':
                        # This is a matchup header
                        if '@' in elem_text or 'vs' in elem_text.lower():
                            # Extract matchup (remove "opens in a new tab")
                            matchup_text = elem_text.replace('opens in a new tab', '').strip()
                            # Split on newline if present
                            lines = [line.strip() for line in matchup_text.split('\n') if line.strip()]
                            if lines:
                                current_matchup = lines[0]
                                # Check if next line is a date/time
                                if len(lines) > 1 and ('/' in lines[1] or 'PM' in lines[1] or 'AM' in lines[1]):
                                    current_game_time = lines[1]
                                else:
                                    current_game_time = ''
                            logger.debug(f"Found matchup: {current_matchup}")
                    
                    elif tag_name == 'h6':
                        # This is a prop type header - may contain player name + prop type
                        prop_text = elem_text.replace('opens in a new tab', '').strip()
                        if prop_text and len(prop_text) > 2:
                            current_prop_type = prop_text
                            logger.debug(f"Found prop type header: {current_prop_type}")
                    
                    elif tag_name == 'a' and 'sportsbook.draftkings.com' in elem.get_attribute('href'):
                        # This is a prop link
                        prop_url = elem.get_attribute('href')
                        prop_text = elem_text.replace('opens in a new tab', '').strip()
                        
                        # Skip if no meaningful text
                        if not prop_text or len(prop_text) < 2:
                            continue
                        
                        # Skip if it's not actually a prop (just a matchup link)
                        if current_matchup and prop_text == current_matchup:
                            continue
                        
                        # Parse the h6 header to extract player name and actual prop type
                        player_name = None
                        actual_prop_type = current_prop_type
                        
                        # Check if current_prop_type contains "player name + prop type" pattern
                        if current_prop_type:
                            for keyword in prop_keywords:
                                if keyword in current_prop_type:
                                    # Split on the keyword to extract player name
                                    parts = current_prop_type.split(keyword, 1)
                                    if parts[0].strip() and keyword != 'First Points Scorer':
                                        # Player name is before the keyword
                                        player_name = parts[0].strip()
                                        actual_prop_type = keyword
                                        break
                                    elif keyword == 'First Points Scorer':
                                        # For First Points Scorer, player name is in the link text
                                        actual_prop_type = keyword
                                        break
                        
                        # Parse the link text to extract player name
                        lines = [line.strip() for line in prop_text.split('\n') if line.strip()]
                        
                        for line in lines:
                            # If no player name yet and this doesn't look like odds, capture it
                            if not player_name and line and len(line) > 1:
                                # Skip odds values (start with + or -)
                                if line[0] not in ['+', '−', '-']:
                                    # For First Points Scorer, this line is the player name
                                    if actual_prop_type == 'First Points Scorer':
                                        player_name = line
                        
                        # For First Points Scorer, if no player name found, try parent element
                        if actual_prop_type == 'First Points Scorer' and not player_name:
                            try:
                                parent = elem.find_element(By.XPATH, "..")
                                parent_text = parent.text.strip().replace('opens in a new tab', '').strip()
                                parent_lines = [l.strip() for l in parent_text.split('\n') if l.strip()]
                                
                                # Find the player name (skip odds and header)
                                for pline in parent_lines:
                                    # Skip if it's odds
                                    if pline and len(pline) > 1 and pline[0] in ['+', '−', '-']:
                                        continue
                                    # Skip if it's the prop type header
                                    if pline == 'First Points Scorer':
                                        continue
                                    # This should be the player name
                                    if pline and len(pline) > 2:
                                        player_name = pline
                                        break
                            except Exception as e:
                                logger.debug(f"Could not extract FPS player name from parent: {e}")
                        
                        # Skip if we've already seen this player-prop combination
                        player_prop_key = (player_name, actual_prop_type) if player_name else (prop_url, actual_prop_type)
                        if player_prop_key in seen_player_props:
                            continue
                        
                        seen_player_props.add(player_prop_key)
                        
                        # Create record with scrape_time, without game_time
                        record = {
                            'scrape_date': now_et.strftime('%Y-%m-%d'),
                            'scrape_time': now_et.strftime('%H:%M:%S'),
                            'matchup': current_matchup or 'Unknown',
                            'prop_type': actual_prop_type or 'Unknown',
                            'player_name': player_name or '',
                            'prop_url': prop_url
                        }
                        
                        props_data.append(record)
                    
                except Exception as e:
                    logger.debug(f"Error processing element: {e}")
                    continue
            
            logger.info(f"Extracted {len(props_data)} prop records")
            
        except Exception as e:
            logger.error(f"Error extracting props data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Save screenshot for debugging
            est = timezone(timedelta(hours=-5))
            now_et = datetime.now(est)
            screenshot_path = os.path.join(self.output_dir, f'error_screenshot_game_view_{now_et.strftime("%Y%m%d_%H%M%S")}.png')
            try:
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
            except:
                pass
            
        return props_data
    
    def scrape(self) -> List[Dict]:
        """Main scraping method"""
        try:
            self.setup_driver()
            
            logger.info(f"Loading URL: {self.url}")
            self.driver.get(self.url)
            
            # Wait for page to load
            logger.info("Waiting for page to load...")
            time.sleep(15)  # Increased wait time for JavaScript rendering
            
            # Extract data
            props_data = self.extract_props_data()
            
            logger.info(f"Extracted {len(props_data)} player prop records")
            
            return props_data
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []
            
        finally:
            self.close_driver()
    
    def save_data(self, data: List[Dict], suffix: str = "game_view"):
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
        
        # Create sorted_props folder with date subfolder
        date_dir = os.path.join(self.output_dir, 'sorted_props', date_str)
        os.makedirs(date_dir, exist_ok=True)
        
        # Save CSV
        csv_path = os.path.join(date_dir, f'draftkings_props_{suffix}_{timestamp}.csv')
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved CSV to {csv_path}")
        
        # Save JSON
        json_path = os.path.join(date_dir, f'draftkings_props_{suffix}_{timestamp}.json')
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved JSON to {json_path}")


def main():
    """Main execution function"""
    logger.info("="*80)
    logger.info("Starting DraftKings NCAA Basketball Props Scraper (Game View)")
    logger.info("="*80)
    
    scraper = DraftKingsGameViewScraper()
    data = scraper.scrape()
    
    if data:
        scraper.save_data(data)
        logger.info(f"Successfully scraped {len(data)} records")
    else:
        logger.warning("No data was scraped")
    
    logger.info("="*80)
    logger.info("DraftKings game view scraper completed")
    logger.info("="*80)


if __name__ == '__main__':
    main()
