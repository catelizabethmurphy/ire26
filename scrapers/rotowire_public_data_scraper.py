"""
RotoWire College Basketball Player Props Scraper - JSON Version
Extracts data directly from the embedded JSON on the page
"""

import os
import re
import json
import time
import logging
from datetime import datetime
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


class RotoWireJSONScraper:
    """Scraper that extracts JSON data from RotoWire page"""
    
    def __init__(self, output_dir: str = None):
        self.url = 'https://www.rotowire.com/betting/college-basketball/player-props.php'
        
        # Use absolute path based on project root
        if output_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(project_root, 'data', 'rotowire_props')
        
        self.output_dir = output_dir
        self.driver = None
        os.makedirs(output_dir, exist_ok=True)
        
    def setup_driver(self):
        """Set up Selenium WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome WebDriver initialized")
        
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")
            
    def extract_json_data(self, page_source: str) -> Dict[str, List[Dict]]:
        """Extract player props data from embedded JSON in page source"""
        data = {
            'points': [],
            'rebounds': [],
            'assists': [],
            'pts_reb_ast': []
        }
        
        # Pattern to find data arrays in JavaScript
        # Looking for patterns like: data: [{...player data...}]
        patterns = {
            'points': r'data:\s*(\[{.*?"mgm_pts".*?}\])',
            'rebounds': r'data:\s*(\[{.*?"mgm_reb".*?}\])',
            'assists': r'data:\s*(\[{.*?"mgm_ast".*?}\])',
            'pts_reb_ast': r'data:\s*(\[{.*?"mgm_pra".*?}\])'
        }
        
        for stat_type, pattern in patterns.items():
            matches = re.findall(pattern, page_source, re.DOTALL)
            
            for match in matches:
                try:
                    # Clean up the JSON string
                    json_str = match.replace('\n', '').replace('\r', '')
                    # Parse JSON
                    players = json.loads(json_str)
                    data[stat_type].extend(players)
                    logger.info(f"Extracted {len(players)} players for {stat_type}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for {stat_type}: {e}")
                    continue
                    
        return data
        
    def flatten_player_data(self, all_data: Dict[str, List[Dict]]) -> List[Dict]:
        """Flatten and combine all player data"""
        flattened = []
        seen_keys = set()  # Track unique player-stat combinations
        
        for stat_type, players in all_data.items():
            for player in players:
                # Create unique key to identify duplicates
                unique_key = f"{player.get('playerID', '')}_{player.get('gameID', '')}_{stat_type}"
                
                # Skip if we've already seen this player-stat combination
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)
                
                # Add sportsbook data based on stat type
                suffix_map = {'points': 'pts', 'rebounds': 'reb', 'assists': 'ast', 'pts_reb_ast': 'pra'}
                suffix = suffix_map.get(stat_type, 'pts')
                
                sportsbooks = ['draftkings', 'fanduel', 'mgm', 'betrivers', 'caesars', 'hardrock', 'thescore']
                
                # Check if at least one sportsbook has a line for this stat
                has_any_line = False
                sportsbook_data = {}
                for book in sportsbooks:
                    line_key = f'{book}_{suffix}'
                    
                    line_value = player.get(line_key)
                    sportsbook_data[f'{book}_line'] = line_value
                    
                    # Check if this book has a line (not null and not empty string)
                    if line_value is not None and line_value != '':
                        has_any_line = True
                
                # Only add record if at least one sportsbook has a line
                if not has_any_line:
                    continue
                
                # Get current time in Eastern Time
                from datetime import timezone, timedelta
                est = timezone(timedelta(hours=-5))
                now_et = datetime.now(est)
                # Use previous day's date for scrape_date (since we're scraping early morning)
                prev_day = now_et - timedelta(days=1)
                
                # Create a simplified record
                record = {
                    'scrape_date': now_et.strftime('%Y-%m-%d'),
                    'scrape_time': now_et.strftime('%H:%M:%S'),
                    'stat_type': stat_type,
                    'player_name': player.get('name', ''),
                    'first_name': player.get('firstName', ''),
                    'last_name': player.get('lastName', ''),
                    'team': player.get('team', ''),
                    'opponent': player.get('opp', ''),
                    'game_id': player.get('gameID', ''),
                    'player_id': player.get('playerID', '')
                }
                
                # Add the sportsbook data we collected
                record.update(sportsbook_data)
                
                flattened.append(record)
                
        return flattened
        
    def scrape(self) -> List[Dict]:
        """Main scraping method"""
        try:
            self.setup_driver()
            
            logger.info(f"Loading URL: {self.url}")
            self.driver.get(self.url)
            
            # Wait for page to load
            time.sleep(10)
            
            # Get page source
            page_source = self.driver.page_source
            
            # Extract JSON data
            logger.info("Extracting JSON data from page...")
            all_data = self.extract_json_data(page_source)
            
            # Flatten the data
            flattened_data = self.flatten_player_data(all_data)
            
            logger.info(f"Successfully extracted {len(flattened_data)} total records")
            
            return flattened_data
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []
        finally:
            self.close_driver()
            
    def save_to_csv(self, data: List[Dict]):
        """Save data to CSV"""
        if not data:
            logger.warning("No data to save")
            return
            
        # Create date-based subfolder using Eastern Time (current day)
        from datetime import timezone, timedelta
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        date_str = now_et.strftime('%Y-%m-%d')
        date_folder = os.path.join(self.output_dir, date_str)
        os.makedirs(date_folder, exist_ok=True)
        
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        filename = f'rotowire_props_{timestamp}.csv'
        filepath = os.path.join(date_folder, filename)
        
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        logger.info(f"Data saved to {filepath}")

        
    def save_to_json(self, data: List[Dict]):
        """Save data to JSON"""
        if not data:
            logger.warning("No data to save")
            return
            
        # Create date-based subfolder using Eastern Time (current day)
        from datetime import timezone, timedelta
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        date_str = now_et.strftime('%Y-%m-%d')
        date_folder = os.path.join(self.output_dir, date_str)
        os.makedirs(date_folder, exist_ok=True)
        
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        filename = f'rotowire_props_{timestamp}.json'
        filepath = os.path.join(date_folder, filename)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Data saved to {filepath}")


def main():
    logger.info("="*80)
    logger.info("Starting RotoWire JSON scraper")
    logger.info("="*80)
    
    scraper = RotoWireJSONScraper()
    data = scraper.scrape()
    
    if data:
        scraper.save_to_csv(data)
        scraper.save_to_json(data)
        logger.info("Scraping completed successfully!")
    else:
        logger.warning("No data was scraped")


if __name__ == '__main__':
    main()
