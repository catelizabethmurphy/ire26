"""
ESPN D1 Men's College Basketball Schedule Scraper - March Madness Tournament Mode
Scrapes TODAY'S schedule at 2 AM when tournament games are announced
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta, timezone
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


class ESPNScheduleScraperTournament:
    """Scraper for ESPN college basketball schedule during March Madness
    
    Designed to run at 2 AM ET to scrape TODAY'S tournament games.
    Data is saved to today's date folder since games are announced day-of.
    """
    
    def __init__(self, output_dir: str = None, target_date: str = None):
        """
        Initialize scraper
        
        Args:
            output_dir: Directory to save scraped data
            target_date: Optional date string in YYYYMMDD format. If None, uses today.
        """
        # Use Eastern Time
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        
        # Use today's date (tournament games are announced same day)
        if target_date:
            # Allow manual override for testing or catchup
            self.game_date = datetime.strptime(target_date, '%Y%m%d')
            date_param = target_date
        else:
            self.game_date = now_et
            date_param = self.game_date.strftime('%Y%m%d')
        
        # ESPN URL with date parameter for today's games
        self.url = f'https://www.espn.com/mens-college-basketball/schedule/_/date/{date_param}'
        
        # Use absolute path based on project root
        if output_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.output_dir = os.path.join(project_root, 'data', 'espn_schedules')
        else:
            self.output_dir = output_dir
        
        self.driver = None
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info(f"Tournament Mode: Scraping games for {self.game_date.strftime('%Y-%m-%d')}")
    
    @staticmethod
    def extract_seed(team_full: str) -> str:
        """Extract tournament seed from team name
        
        Args:
            team_full: Full team string like "1 Duke" or "11 Michigan St." or "v 16 Howard"
            
        Returns:
            Seed number as string, or empty string if no seed
        """
        import re
        # Remove @ symbol, v symbol, and extra spaces
        clean_text = team_full.replace('@', '').replace('v', '').strip()
        # Look for a number at the start (1-16 for tournament seeds)
        match = re.match(r'^(\d{1,2})\s+', clean_text)
        if match:
            seed = int(match.group(1))
            if 1 <= seed <= 16:
                return match.group(1)
        return ""
    
    @staticmethod
    def parse_odds(odds_text: str) -> dict:
        """Parse betting odds from odds cell
        
        Args:
            odds_text: Text like "Line: UMBC -1.5 O/U: 139.5" or "Line: UMBC -1.5\nO/U: 139.5"
            
        Returns:
            Dictionary with spread_line, spread_team, over_under fields
        """
        import re
        
        result = {
            'spread_line': '',
            'spread_team': '',
            'over_under': ''
        }
        
        if not odds_text:
            return result
        
        # Extract line/spread (e.g., "Line: UMBC -1.5" or "UMBC -1.5")
        line_match = re.search(r'(?:Line:\s*)?([A-Za-z\s\.&]+?)\s+([-+]?\d+\.?\d*)', odds_text)
        if line_match:
            result['spread_team'] = line_match.group(1).strip()
            result['spread_line'] = line_match.group(2).strip()
        
        # Extract over/under (e.g., "O/U: 139.5" or just "139.5")
        ou_match = re.search(r'O/U:\s*(\d+\.?\d*)', odds_text)
        if ou_match:
            result['over_under'] = ou_match.group(1).strip()
        
        return result
    
    @staticmethod
    def parse_game_note(game_note: str) -> Dict[str, str]:
        """Parse game note into tournament, round, and region
        
        Args:
            game_note: String like "NCAA Men's Basketball Championship - Midwest Region - First Four"
                       or "NIT Season Tip-Off - First Round"
        
        Returns:
            Dictionary with tournament, round, and region fields
        """
        import re
        
        result = {
            'tournament': '',
            'round': '',
            'region': ''
        }
        
        if not game_note:
            return result
        
        # Determine tournament type
        if 'NCAA Men\'s Basketball Championship' in game_note or 'NCAA Tournament' in game_note:
            result['tournament'] = 'NCAA Tournament'
        elif 'NCAA' in game_note:
            result['tournament'] = 'NCAA Tournament'
        elif 'NIT' in game_note:
            result['tournament'] = 'NIT'
        elif game_note:
            result['tournament'] = game_note.split('-')[0].strip()
        else:
            result['tournament'] = ''
        
        # Extract region (only for NCAA tournament)
        region_match = re.search(r'(East|West|South|Midwest|Southeast|Southwest)\s+Region', game_note, re.IGNORECASE)
        if region_match:
            result['region'] = region_match.group(1)
        
        # Extract round - look for various round patterns
        # Order matters: more specific patterns must come before generic ones
        round_patterns = [
            r'First Four',
            r'First Round',
            r'1st Round',
            r'Second Round',
            r'2nd Round',
            r'Third Round',
            r'3rd Round',
            r'Sweet 16',
            r'Sweet Sixteen',
            r'Elite Eight',
            r'Elite 8',
            r'Regional Semifinal',
            r'Regional Final',
            r'Final Four',
            r'National Championship',
            r'Semifinals',
            r'Semifinal',
            r'Quarterfinals',
            r'Quarterfinal',
            r'Championship',  # Generic - must be last to avoid false matches
        ]
        
        for pattern in round_patterns:
            if re.search(pattern, game_note, re.IGNORECASE):
                result['round'] = re.search(pattern, game_note, re.IGNORECASE).group(0)
                break
        
        return result
        
    def setup_driver(self):
        """Set up Selenium WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Set timezone to Eastern Time to get correct game times from ESPN
        chrome_options.add_experimental_option('prefs', {
            'profile.default_content_setting_values.geolocation': 1,
            'intl.accept_languages': 'en-US,en'
        })
        chrome_options.add_argument('--lang=en-US')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Set timezone via CDP (Chrome DevTools Protocol)
        self.driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': 'America/New_York'})
        logger.info("Chrome WebDriver initialized with Eastern Time timezone")
        
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")
            
    def scrape_schedule(self) -> List[Dict]:
        """Scrape schedule data from ESPN"""
        games = []
        
        try:
            logger.info(f"Loading URL: {self.url}")
            self.driver.get(self.url)
            
            # Wait for schedule to load
            time.sleep(5)
            
            # Try to find schedule tables
            try:
                # Look for the main date header (appears once for all games on that day)
                current_date = None
                date_headers = self.driver.find_elements(By.CSS_SELECTOR, ".Table__Title")
                if len(date_headers) > 0:
                    current_date = date_headers[0].text.strip()
                    logger.info(f"Found date: {current_date}")
                else:
                    logger.warning("No date header found")
                
                # First, get all gameNote elements on the page and log them
                all_game_notes = self.driver.find_elements(By.CSS_SELECTOR, ".gameNote")
                logger.info(f"Found {len(all_game_notes)} gameNote elements on page")
                for i, note in enumerate(all_game_notes[:5]):  # Log first 5
                    logger.info(f"  GameNote {i}: '{note.text.strip()}'")
                
                # Also try to find the schedule container div
                schedule_divs = self.driver.find_elements(By.CSS_SELECTOR, ".ScheduleTables, .Schedule")
                logger.info(f"Found {len(schedule_divs)} schedule container divs")
                
                # Look for all game rows and their section headers
                tables = self.driver.find_elements(By.CSS_SELECTOR, ".Schedule__Table, table.Table")
                logger.info(f"Found {len(tables)} schedule tables")
                
                # Try getting all rows across all tables and process with game notes
                all_rows = []
                for table in tables:
                    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
                    all_rows.extend([(table, row) for row in rows])
                
                logger.info(f"Total rows to process: {len(all_rows)}")
                
                # Build a map of game notes to their Y positions
                note_positions = []
                for note in all_game_notes:
                    try:
                        y_pos = note.location['y']
                        text = note.text.strip()
                        if text:  # Only include non-empty notes
                            note_positions.append((y_pos, text))
                    except:
                        pass
                
                note_positions.sort()  # Sort by Y position
                logger.info(f"Note positions: {note_positions}")
                
                # Build mapping of rows to notes more intelligently
                # Each game note typically precedes the games it describes
                row_game_notes = []
                for table, row in all_rows:
                    try:
                        row_y = row.location['y']
                        row_game_notes.append(row_y)
                    except:
                        row_game_notes.append(None)
                
                logger.info(f"First 5 row Y positions: {row_game_notes[:5]}")
                logger.info(f"All row Y positions: {row_game_notes}")
                
                # Strategy: Each game note appears AFTER the game(s) it describes
                # So for each row, find the first game note that appears after it
                for idx, (table, row) in enumerate(all_rows):
                    try:
                        # Get Eastern Time
                        est = timezone(timedelta(hours=-5))
                        now_et = datetime.now(est)
                        
                        game_data = {
                            'scrape_date': now_et.strftime('%Y-%m-%d'),
                            'scrape_time': now_et.strftime('%H:%M:%S'),
                            'game_date': current_date
                        }
                        
                        # Find the game note that appears immediately AFTER this row
                        current_game_note = ''
                        try:
                            row_y = row_game_notes[idx]
                            if row_y is not None:
                                # Find the first game note that comes after this row
                                for note_y, note_text in note_positions:
                                    if note_y > row_y:
                                        # First note after this row - use it
                                        current_game_note = note_text
                                        break
                                
                                # If no note found after, it might be the last game under the last note
                                # Use the previous game's note by looking at what note came before
                                if not current_game_note and note_positions:
                                    # Use the last note on the page
                                    current_game_note = note_positions[-1][1]
                        except Exception as e:
                            logger.debug(f"Could not get row position: {e}")
                        
                        # Parse the game note for this row
                        parsed_game_info = self.parse_game_note(current_game_note)
                        game_data.update(parsed_game_info)
                        
                        # Get all cells in the row
                        cells = row.find_elements(By.TAG_NAME, "td")
                        
                        if len(cells) >= 2:
                            # Cell 0: Away team
                            away_cell = cells[0]
                            away_links = away_cell.find_elements(By.TAG_NAME, "a")
                            if away_links:
                                # Get the last link (team name, not ranking)
                                game_data['away_team'] = away_links[-1].text.strip()
                                # Get full text to capture seed
                                full_away = away_cell.text.strip().replace('\n', ' ')
                                game_data['away_team_full'] = full_away
                                # Extract tournament seed
                                game_data['away_team_seed'] = self.extract_seed(full_away)
                            
                            # Cell 1: Home team
                            home_cell = cells[1]
                            home_links = home_cell.find_elements(By.TAG_NAME, "a")
                            if home_links:
                                game_data['home_team'] = home_links[-1].text.strip()
                                full_home = home_cell.text.strip().replace('\n', ' ')
                                game_data['home_team_full'] = full_home
                                # Extract tournament seed
                                game_data['home_team_seed'] = self.extract_seed(full_home)
                            
                            # Cell 2: Game time
                            if len(cells) > 2:
                                game_data['game_time'] = cells[2].text.strip()
                            
                            # Check if game is finished (game_time contains a score like "ILL 78, NEB 69")
                            is_finished = game_data.get('game_time', '').count(',') == 1 and any(c.isdigit() for c in game_data.get('game_time', ''))
                            
                            # Cell 3: TV network OR winner high scorer (if finished) OR betting info
                            if len(cells) > 3:
                                tv_cell = cells[3]
                                tv = ''
                                
                                # Try to find TV network image with alt tag first
                                try:
                                    tv_img = tv_cell.find_element(By.TAG_NAME, "img")
                                    tv = tv_img.get_attribute("alt").strip()
                                except:
                                    # Fall back to text if no image found
                                    tv = tv_cell.text.strip()
                                
                                if tv:
                                    if is_finished:
                                        # Parse winner high scorer (e.g., "Keaton Wagler28 Pts")
                                        game_data['winner_high'] = tv
                                        # Try to split into player and points
                                        import re
                                        match = re.match(r'(.+?)(\d+)\s*Pts', tv)
                                        if match:
                                            game_data['winner_high_player'] = match.group(1).strip()
                                            game_data['winner_high_pts'] = match.group(2)
                                    else:
                                        game_data['tv_network'] = tv
                            
                            # Cell 4: Additional info (tickets) OR loser high scorer (if finished)
                            if len(cells) > 4:
                                info = cells[4].text.strip()
                                if info:
                                    if is_finished:
                                        # Parse loser high scorer (e.g., "Braden Frager20 Pts")
                                        game_data['loser_high'] = info
                                        # Try to split into player and points
                                        import re
                                        match = re.match(r'(.+?)(\d+)\s*Pts', info)
                                        if match:
                                            game_data['loser_high_player'] = match.group(1).strip()
                                            game_data['loser_high_pts'] = match.group(2)
                                    else:
                                        game_data['tickets_info'] = info
                            
                            # Cell 5: Venue (important for tournament - shows city/region)
                            if len(cells) > 5:
                                venue = cells[5].text.strip()
                                if venue:
                                    game_data['venue'] = venue
                            
                            # Cell 6: Odds (DraftKings betting lines)
                            if len(cells) > 6:
                                odds_text = cells[6].text.strip()
                                if odds_text:
                                    odds_data = self.parse_odds(odds_text)
                                    game_data.update(odds_data)
                            
                            # Only add if we have team names
                            if game_data.get('away_team') and game_data.get('home_team'):
                                games.append(game_data)
                                logger.debug(f"Added game: {game_data['away_team']} @ {game_data['home_team']}")
                                
                    except Exception as e:
                        logger.debug(f"Error processing row: {e}")
                        continue
                            
            except Exception as e:
                logger.error(f"Error finding schedule elements: {e}")
                
            logger.info(f"Successfully scraped {len(games)} games")
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            
        return games
        
    def save_to_csv(self, data: List[Dict]):
        """Save data to CSV in today's date folder"""
        if not data:
            logger.warning("No data to save")
            return
            
        # Create date-based subfolder for today's date (tournament games announced same day)
        date_str = self.game_date.strftime('%Y-%m-%d')
        date_folder = os.path.join(self.output_dir, date_str)
        os.makedirs(date_folder, exist_ok=True)
        
        # Use Eastern Time
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        filename = f'espn_schedule_{timestamp}.csv'
        filepath = os.path.join(date_folder, filename)
        
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        logger.info(f"Data saved to {filepath}")
        
    def save_to_json(self, data: List[Dict]):
        """Save data to JSON in today's date folder"""
        if not data:
            logger.warning("No data to save")
            return
            
        # Create date-based subfolder for today's date (tournament games announced same day)
        date_str = self.game_date.strftime('%Y-%m-%d')
        date_folder = os.path.join(self.output_dir, date_str)
        os.makedirs(date_folder, exist_ok=True)
        
        # Use Eastern Time
        est = timezone(timedelta(hours=-5))
        now_et = datetime.now(est)
        timestamp = now_et.strftime('%Y%m%d_%H%M%S')
        filename = f'espn_schedule_{timestamp}.json'
        filepath = os.path.join(date_folder, filename)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Data saved to {filepath}")
        
    def scrape(self) -> List[Dict]:
        """Main scraping method"""
        try:
            self.setup_driver()
            games = self.scrape_schedule()
            return games
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []
        finally:
            self.close_driver()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape ESPN schedule for March Madness')
    parser.add_argument('--date', help='Optional date in YYYYMMDD format (default: today)', default=None)
    args = parser.parse_args()
    
    logger.info("="*80)
    logger.info("Starting ESPN Schedule scraper - MARCH MADNESS TOURNAMENT MODE")
    logger.info("="*80)
    
    scraper = ESPNScheduleScraperTournament(target_date=args.date)
    data = scraper.scrape()
    
    if data:
        scraper.save_to_csv(data)
        scraper.save_to_json(data)
        logger.info("Scraping completed successfully!")
        logger.info(f"Scraped {len(data)} games")
    else:
        logger.warning("No data was scraped")


if __name__ == '__main__':
    main()
