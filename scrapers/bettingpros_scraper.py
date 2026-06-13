"""
BettingPros College Basketball Player Props Scraper
Extracts player prop data including opening lines and individual sportsbook odds
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BettingProsScraper:
    """Scraper for BettingPros player props data"""
    
    def __init__(self, output_dir: str = None, target_date: str = None):
        self.base_url = 'https://www.bettingpros.com/ncaab/odds/player-props/'
        self.target_date = target_date
        
        # Add date parameter to base URL if provided
        if target_date:
            self.base_url = f'{self.base_url}?date={target_date}'
        
        # Use absolute path based on project root
        if output_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(project_root, 'data', 'bettingpros_props')
        
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
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome WebDriver initialized")
        
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")
    
    def get_player_links(self) -> List[Dict[str, str]]:
        """Get all player profile links from the main page"""
        logger.info(f"Loading main page: {self.base_url}")
        self.driver.get(self.base_url)
        time.sleep(5)  # Wait for page to load
        
        player_links = []
        
        try:
            # Find all player links - they have href patterns like /ncaab/odds/player-props/player-name/
            links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/ncaab/odds/player-props/']")
            
            for link in links:
                href = link.get_attribute('href')
                # Only include individual player pages (not the main page)
                # Remove query parameters for comparison to check base URL structure
                base_href = href.split('?')[0] if href else ''
                base_main_url = self.base_url.split('?')[0]
                
                if href and base_href != base_main_url and (href.endswith('/') or '?' in href):
                    try:
                        # Try to extract player name from the link text
                        text = link.text.strip()
                        if text and 'View' in text and 'props' in text:
                            # Format is typically: "K. Boswell\nILL - G\nView 2 props"
                            lines = [l.strip() for l in text.split('\n') if l.strip() and not (l.strip().startswith('View') and 'props' in l)]
                            
                            player_name = ''
                            team = ''
                            position = ''
                            
                            # Line 1: Player name (abbreviated)
                            if len(lines) >= 1:
                                player_name = lines[0]
                            
                            # Line 2: Team - Position (e.g., "ILL - G")
                            if len(lines) >= 2 and ' - ' in lines[1]:
                                parts = lines[1].split(' - ')
                                team = parts[0].strip()
                                if len(parts) > 1:
                                    position = parts[1].strip()
                            
                            if not player_name:
                                # Fallback: extract from URL
                                name_match = re.search(r'/player-props/([^/]+)/', href)
                                if name_match:
                                    player_name = name_match.group(1).replace('-', ' ').title()
                            
                            player_links.append({
                                'name': player_name,
                                'team': team,
                                'position': position,
                                'url': href
                            })
                    except:
                        continue
            
            # Remove duplicates
            seen = set()
            unique_links = []
            for link in player_links:
                if link['url'] not in seen:
                    seen.add(link['url'])
                    unique_links.append(link)
            
            logger.info(f"Found {len(unique_links)} unique player profile links")
            return unique_links
            
        except Exception as e:
            logger.error(f"Error getting player links: {e}")
            return []
    
    def get_sportsbook_order(self) -> List[str]:
        """Extract the order of sportsbooks from the page header"""
        try:
            # Find the header section that shows sportsbook logos
            # Look for a container that has the sportsbook images in order
            # Try to find elements that are specifically in a header or sticky bar
            
            # First try: find sticky header or odds header
            possible_headers = []
            
            # Look for elements with header-like classes
            header_candidates = self.driver.find_elements(By.CSS_SELECTOR, "[class*='header'], [class*='sticky'], [class*='odds-header']")
            
            sportsbooks = []
            
            # Method 1: Try to find images in a specific header container
            for container in header_candidates:
                imgs = container.find_elements(By.CSS_SELECTOR, "img")
                if len(imgs) >= 5:  # Should have multiple sportsbook logos
                    temp_books = []
                    for img in imgs:
                        src = img.get_attribute('src') or ""
                        if '/books/' in src or 'sportsbook' in src.lower():
                            filename = src.split('/')[-1]
                            book_name = filename.replace('.svg', '').replace('.png', '').replace('.webp', '')
                            book_name = book_name.replace('-sb-dark', '').replace('-dark', '').replace('-logo', '').replace('-sb', '')
                            book_name = book_name.replace('_', ' ').replace('-', ' ').title().strip()
                            if book_name:
                                temp_books.append(book_name)
                    
                    if len(temp_books) >= 5:
                        sportsbooks = temp_books
                        break
            
            # Method 2: If header method didn't work, get all images but remove duplicates in order
            if not sportsbooks:
                all_imgs = self.driver.find_elements(By.CSS_SELECTOR, "img")
                seen = set()
                
                for img in all_imgs:
                    src = img.get_attribute('src') or ""
                    if '/books/' in src or 'sportsbook' in src.lower():
                        filename = src.split('/')[-1]
                        book_name = filename.replace('.svg', '').replace('.png', '').replace('.webp', '')
                        book_name = book_name.replace('-sb-dark', '').replace('-dark', '').replace('-logo', '').replace('-sb', '')
                        book_name = book_name.replace('_', ' ').replace('-', ' ').title().strip()
                        
                        if book_name and book_name not in seen:
                            seen.add(book_name)
                            sportsbooks.append(book_name)
            
            logger.info(f"  Found sportsbook order: {sportsbooks[:10]}...")  # Show first 10
            return sportsbooks
            
        except Exception as e:
            logger.warning(f"Error getting sportsbook order: {e}")
            return []
    
    def scrape_player_props(self, player_url: str, player_name: str, player_team: str = '', player_position: str = '') -> List[Dict]:
        """Scrape props for a single player"""
        logger.info(f"Scraping props for {player_name}")
        
        try:
            # Add date parameter to player URL if specified
            if self.target_date:
                if '?' in player_url:
                    player_url = f'{player_url}&date={self.target_date}'
                else:
                    player_url = f'{player_url}?date={self.target_date}'
            
            self.driver.get(player_url)
            time.sleep(3)  # Wait for page to load
            
            # Extract game info from page body text
            # Format is typically: "E. Elmer\nF - M-OH at WMU\nToday\n6:00 PM EST"
            game_matchup = ''
            game_date = ''
            game_time = ''
            
            try:
                # Get the full body text and search for the game info pattern
                body = self.driver.find_element(By.TAG_NAME, 'body')
                full_text = body.text
                lines = full_text.split('\n')
                
                # Look for pattern like "F - M-OH at WMU" in the lines
                for i, line in enumerate(lines):
                    line = line.strip()
                    # Check if this line contains abbreviated player name (e.g., "E. Elmer")
                    if line and '. ' in line:
                        # Check if it's followed by position and matchup
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            # Look for pattern like "F - M-OH at WMU" or "G - TEAM at OPP"
                            if ' at ' in next_line and ' - ' in next_line:
                                # This is the game info line (e.g., "F - M-OH at WMU")
                                parts = next_line.split(' - ', 1)
                                
                                # Extract position (first part before " - ")
                                if not player_position and len(parts[0].strip()) <= 2:
                                    player_position = parts[0].strip()
                                
                                # Extract game matchup and team
                                if len(parts) > 1:
                                    game_matchup = parts[1].strip()
                                    
                                    # Extract player's team from matchup (e.g., "M-OH at WMU")
                                    if not player_team:
                                        if ' at ' in game_matchup:
                                            matchup_parts = game_matchup.split(' at ')
                                            player_team = matchup_parts[0].strip()
                                
                                # Get game date and time from following lines
                                if i + 2 < len(lines):
                                    potential_date = lines[i + 2].strip()
                                    # Check if it looks like a date (Today, Tomorrow, or day of week)
                                    if potential_date and (potential_date in ['Today', 'Tomorrow'] or len(potential_date.split()) <= 2):
                                        game_date = potential_date
                                if i + 3 < len(lines):
                                    potential_time = lines[i + 3].strip()
                                    # Check if it looks like a time (has PM or AM or EST, etc.)
                                    if 'PM' in potential_time or 'AM' in potential_time or 'EST' in potential_time or 'ET' in potential_time:
                                        game_time = potential_time
                                break
            except Exception as e:
                logger.debug(f"  Error extracting game info: {e}")
            
            # Get the full player name from the page header
            try:
                # Look for h1 which should contain the full player name
                h1_elements = self.driver.find_elements(By.CSS_SELECTOR, "h1")
                for elem in h1_elements:
                    text = elem.text.strip()
                    # Pattern is typically: "Kylan Boswell NCAAB Player Props Odds"
                    if 'NCAAB' in text and 'Player Props' in text:
                        # Extract just the player name (before "NCAAB")
                        full_name = text.split('NCAAB')[0].strip()
                        if full_name and len(full_name) > 3:
                            player_name = full_name
                            logger.info(f"  Found full player name: {player_name}")
                            break
            except Exception as e:
                logger.debug(f"  Error extracting full player name: {e}")
            
            # Get the order of sportsbooks from the page
            sportsbook_order = self.get_sportsbook_order()
            
            props_data = []
            
            # Find all prop offer rows using the actual BettingPros structure
            try:
                rows = self.driver.find_elements(By.CSS_SELECTOR, ".odds-offer")
                logger.info(f"  Found {len(rows)} prop rows")
                
                for row in rows:
                    try:
                        # Get all items in this row
                        items = row.find_elements(By.CSS_SELECTOR, ".odds-offer__item")
                        
                        if len(items) < 3:
                            continue
                        
                        # First item is the market label
                        market_label = items[0].text.strip()
                        if not market_label:
                            continue
                        
                        # Extract sportsbook odds (start from index 4: skip label, OPEN, BEST ODDS, CONSENSUS)
                        sportsbook_data = {}
                        
                        # Map the remaining items to sportsbooks using the order we found
                        for i in range(4, len(items)):
                            try:
                                sb_item = items[i]
                                
                                # Determine which sportsbook this column represents
                                sb_index = i - 4
                                
                                if sb_index >= len(sportsbook_order):
                                    continue
                                
                                book_name = sportsbook_order[sb_index]
                                
                                # Get the odds cells for this sportsbook
                                sb_cells = sb_item.find_elements(By.CSS_SELECTOR, ".odds-cell")
                                
                                if len(sb_cells) >= 1:
                                    # Check if first cell has actual odds (not no-line)
                                    first_cell_class = sb_cells[0].get_attribute("class") or ""
                                    
                                    if "odds-cell--no-line" not in first_cell_class:
                                        try:
                                            # Over odds
                                            over_line_elem = sb_cells[0].find_elements(By.CSS_SELECTOR, ".odds-cell__line")
                                            over_cost_elem = sb_cells[0].find_elements(By.CSS_SELECTOR, ".odds-cell__cost")
                                            
                                            # Under odds (if available)
                                            under_line_elem = []
                                            under_cost_elem = []
                                            if len(sb_cells) >= 2:
                                                under_cell_class = sb_cells[1].get_attribute("class") or ""
                                                if "odds-cell--no-line" not in under_cell_class:
                                                    under_line_elem = sb_cells[1].find_elements(By.CSS_SELECTOR, ".odds-cell__line")
                                                    under_cost_elem = sb_cells[1].find_elements(By.CSS_SELECTOR, ".odds-cell__cost")
                                            
                                            if over_line_elem and over_cost_elem:
                                                over_line = over_line_elem[0].text.strip()
                                                over_cost = over_cost_elem[0].text.strip()
                                                
                                                # Extract numeric line value
                                                line_value = None
                                                try:
                                                    # Extract number from over_line (e.g., "O 6.5" -> 6.5)
                                                    line_match = re.search(r'(\d+\.?\d*)', over_line)
                                                    if line_match:
                                                        line_value = float(line_match.group(1))
                                                except:
                                                    pass
                                                
                                                # Build raw odds string
                                                book_key = book_name.lower().replace(" ", "_").replace("-", "_")
                                                
                                                if under_line_elem and under_cost_elem:
                                                    under_line = under_line_elem[0].text.strip()
                                                    under_cost = under_cost_elem[0].text.strip()
                                                    raw_value = f"{over_line}{over_cost}/{under_line}{under_cost}"
                                                else:
                                                    # Only over available
                                                    raw_value = f"{over_line}{over_cost}"
                                                
                                                sportsbook_data[f"{book_key}_raw"] = raw_value
                                                if line_value is not None:
                                                    sportsbook_data[f"{book_key}_line"] = line_value
                                        except Exception as e:
                                            logger.debug(f"    Error extracting odds from {book_name}: {e}")
                                            pass
                            except Exception as e:
                                logger.debug(f"    Error processing sportsbook item {i}: {e}")
                                continue
                        
                        # Only add record if at least one sportsbook has data
                        if sportsbook_data:
                            logger.info(f"  Captured {len(sportsbook_data)} sportsbooks for {market_label}")
                            
                            # Create record
                            record = {
                                'player_name': player_name,
                                'team': player_team,
                                'position': player_position,
                                'market_type': market_label,
                                'game_matchup': game_matchup,
                                'game_date': game_date,
                                'game_time': game_time,
                                'player_url': player_url
                            }
                            
                            # Add sportsbook data
                            record.update(sportsbook_data)
                            
                            props_data.append(record)
                            logger.debug(f"  Added prop: {market_label}")
                        
                    except Exception as e:
                        logger.debug(f"Error processing row: {e}")
                        continue
                
            except Exception as e:
                logger.warning(f"Error finding prop rows for {player_name}: {e}")
            
            return props_data
            
        except Exception as e:
            logger.error(f"Error scraping {player_name}: {e}")
            return []
    
    def scrape(self) -> List[Dict]:
        """Main scraping method"""
        all_props = []
        
        try:
            self.setup_driver()
            
            # Get all player links
            player_links = self.get_player_links()
            
            if not player_links:
                logger.warning("No player links found")
                return []
            
            # Scrape each player's props
            for i, player_info in enumerate(player_links, 1):
                logger.info(f"Processing player {i}/{len(player_links)}: {player_info['name']}")
                
                player_props = self.scrape_player_props(
                    player_info['url'], 
                    player_info['name'],
                    player_info.get('team', ''),
                    player_info.get('position', '')
                )
                
                if player_props:
                    all_props.extend(player_props)
                    logger.info(f"  Found {len(player_props)} props")
                else:
                    logger.info(f"  No props found")
                
                # Small delay between requests
                time.sleep(2)
            
            # Add timestamp to all records
            est = timezone(timedelta(hours=-5))
            now_et = datetime.now(est)
            
            for prop in all_props:
                prop['scrape_date'] = now_et.strftime('%Y-%m-%d')
                prop['scrape_time'] = now_et.strftime('%H:%M:%S')
            
            logger.info(f"Total props scraped: {len(all_props)}")
            return all_props
            
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
        
        # Create date-based subfolder
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        date_str = now_et.strftime('%Y-%m-%d')
        date_folder = os.path.join(self.output_dir, date_str)
        os.makedirs(date_folder, exist_ok=True)
        
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        filename = f'bettingpros_props_{timestamp}.csv'
        filepath = os.path.join(date_folder, filename)
        
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        logger.info(f"Data saved to {filepath}")
        
        # Also save latest version in the main directory

    
    def save_to_json(self, data: List[Dict]):
        """Save data to JSON"""
        if not data:
            logger.warning("No data to save")
            return
        
        # Create date-based subfolder
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        date_str = now_et.strftime('%Y-%m-%d')
        date_folder = os.path.join(self.output_dir, date_str)
        os.makedirs(date_folder, exist_ok=True)
        
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        filename = f'bettingpros_props_{timestamp}.json'
        filepath = os.path.join(date_folder, filename)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Data saved to {filepath}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape BettingPros player props')
    parser.add_argument('--date', type=str, help='Target date in YYYY-MM-DD format (e.g., 2026-03-26)')
    args = parser.parse_args()
    
    logger.info("="*80)
    logger.info("Starting BettingPros scraper")
    if args.date:
        logger.info(f"Target date: {args.date}")
    logger.info("="*80)
    
    try:
        scraper = BettingProsScraper(target_date=args.date)
        data = scraper.scrape()
        
        if data:
            scraper.save_to_csv(data)
            scraper.save_to_json(data)
            logger.info("Scraping completed successfully!")
            return 0
        else:
            logger.warning("No data was scraped")
            return 0  # Return 0 even if no data, not a failure
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
