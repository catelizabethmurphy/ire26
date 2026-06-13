import os
import json
import csv
import requests
from datetime import datetime
import time

def fetch_url(url):
    """Fetch URL with proper headers"""
    r = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
    return r

def fetch_game_from_espn(game_id):
    """
    Fetch game box score from ESPN API
    ESPN game IDs are used for NCAA tournament games
    """
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={game_id}"
    
    try:
        r = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error fetching game {game_id}: {e}")
    
    return None

def parse_espn_box_score(game_data, scheduled_date=None):
    """
    Parse box score from ESPN API response
    Args:
        game_data: ESPN API response
        scheduled_date: Scheduled date in YYYY-MM-DD format (overrides UTC timestamp)
    """
    player_stats = []
    
    if not game_data or 'boxscore' not in game_data:
        return player_stats
    
    # Get game info
    game_id = game_data.get('header', {}).get('id', '')
    # Use scheduled date if provided, otherwise fall back to UTC date from API
    if scheduled_date:
        game_date = scheduled_date
    else:
        game_date = game_data.get('header', {}).get('competitions', [{}])[0].get('date', '')
    
    # Get players data (new structure)
    players_data = game_data.get('boxscore', {}).get('players', [])
    
    # Get team info for looking up opponents
    all_teams = [{
        'location': team.get('team', {}).get('location', ''),
        'name': team.get('team', {}).get('name', '')
    } for team in players_data]
    
    for team_data in players_data:
        team_info = team_data.get('team', {})
        team_location = team_info.get('location', '')
        team_mascot = team_info.get('name', '')
        
        # Get opponent
        opponent_location = ''
        opponent_mascot = ''
        for other_team in all_teams:
            if other_team['location'] != team_location or other_team['name'] != team_mascot:
                opponent_location = other_team['location']
                opponent_mascot = other_team['name']
                break
        
        # Get statistics for each player
        statistics = team_data.get('statistics', [])
        
        if not statistics:
            continue
            
        stat_group = statistics[0]  # First stat group has player stats
        athletes = stat_group.get('athletes', [])
        
        for athlete in athletes:
            player_name = athlete.get('athlete', {}).get('displayName', '')
            jersey_raw = athlete.get('athlete', {}).get('jersey', '')
            # Convert to integer, default to 0 if empty or invalid
            try:
                jersey = int(jersey_raw) if jersey_raw else 0
            except (ValueError, TypeError):
                jersey = 0
            
            stats = athlete.get('stats', [])
            
            # Parse stats - ESPN returns them as an array
            # Order: MIN, PTS, FG, 3PT, FT, REB, AST, TO, STL, BLK, OREB, DREB, PF
            minutes = stats[0] if len(stats) > 0 else 0
            pts = stats[1] if len(stats) > 1 else 0
            fg = stats[2] if len(stats) > 2 else '0-0'
            fg3 = stats[3] if len(stats) > 3 else '0-0'
            ft = stats[4] if len(stats) > 4 else '0-0'
            reb = stats[5] if len(stats) > 5 else 0
            ast = stats[6] if len(stats) > 6 else 0
            to = stats[7] if len(stats) > 7 else 0
            stl = stats[8] if len(stats) > 8 else 0
            blk = stats[9] if len(stats) > 9 else 0
            oreb = stats[10] if len(stats) > 10 else 0
            dreb = stats[11] if len(stats) > 11 else 0
            pf = stats[12] if len(stats) > 12 else 0
            
            # Parse made-attempted format and convert to integers
            fgm, fga = fg.split('-') if '-' in str(fg) else (0, 0)
            fg3m, fg3a = fg3.split('-') if '-' in str(fg3) else (0, 0)
            ftm, fta = ft.split('-') if '-' in str(ft) else (0, 0)
            
            # Convert all to int to ensure consistent types
            row = [
                int(game_id), game_date, team_location, team_mascot, 
                opponent_location, opponent_mascot, player_name, int(jersey),
                int(minutes), int(fgm), int(fga), int(fg3m), int(fg3a), int(ftm), int(fta), int(pts),
                int(oreb), int(dreb), int(reb), int(ast), int(to), int(stl), int(blk), int(pf)
            ]
            
            player_stats.append(row)
    
    return player_stats

def scrape_tournament_games_from_date(start_date, end_date=None):
    """
    Scrape games from NCAA tournament by date range
    Dates in format: YYYYMMDD
    """
    print(f"Searching for tournament games from {start_date} to {end_date or start_date}")
    
    # Use ESPN's scoreboard API for the date
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={start_date}&groups=100"
    
    try:
        r = requests.get(url, headers={'User-agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            print(f"Error fetching scoreboard: {r.status_code}")
            return []
        
        data = r.json()
        events = data.get('events', [])
        
        game_ids = []
        for event in events:
            game_id = event.get('id')
            name = event.get('name', '')
            
            # Check if it's a tournament game
            competitions = event.get('competitions', [{}])[0]
            notes = competitions.get('notes', [])
            
            # Tournament games usually have specific notes
            is_tournament = any('tournament' in note.get('headline', '').lower() or 
                              'ncaa' in note.get('headline', '').lower() 
                              for note in notes)
            
            if game_id:
                print(f"Found game: {name} (ID: {game_id})")
                game_ids.append(game_id)
        
        return game_ids
        
    except Exception as e:
        print(f"Error: {e}")
        return []

def scrape_march_madness_box_scores(date_range, output_file=None):
    """
    Main function to scrape March Madness box scores
    
    Args:
        date_range: Single date (YYYYMMDD) or list of dates
        output_file: Path to output CSV (if provided, will save all to one file)
    """
    if isinstance(date_range, str):
        date_range = [date_range]
    
    # Get game IDs for each date and track which date they were scheduled for
    game_to_scheduled_date = {}
    all_game_ids = []
    
    for date in date_range:
        game_ids = scrape_tournament_games_from_date(date)
        for game_id in game_ids:
            scheduled_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            game_to_scheduled_date[game_id] = scheduled_date
        all_game_ids.extend(game_ids)
    
    # Remove duplicates
    all_game_ids = list(set(all_game_ids))
    print(f"\nFound {len(all_game_ids)} unique games")
    
    if not all_game_ids:
        print("No games found!")
        return
    
    # Fetch all games and group by scheduled date
    games_by_date = {}
    
    for i, game_id in enumerate(all_game_ids, 1):
        print(f"\nProcessing game {i}/{len(all_game_ids)}: {game_id}")
        
        game_data = fetch_game_from_espn(game_id)
        
        if game_data:
            # Get scheduled date for this game
            scheduled_date = game_to_scheduled_date.get(game_id)
            player_stats = parse_espn_box_score(game_data, scheduled_date)
            
            if player_stats:
                if scheduled_date:
                    if scheduled_date not in games_by_date:
                        games_by_date[scheduled_date] = []
                    
                    games_by_date[scheduled_date].extend(player_stats)
                    print(f"  Extracted {len(player_stats)} player records (date: {scheduled_date})")
                else:
                    print(f"  Warning: No scheduled date found for game {game_id}")
            else:
                print(f"  No player stats found")
        else:
            print(f"  Failed to fetch game data")
        
        # Be nice to the API
        time.sleep(1)
    
    # Save games grouped by date
    if output_file:
        # If specific output file provided, save all to one file
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_to_csv(output_file, games_by_date)
        print(f"\nBox scores saved to: {output_file}")
        return output_file
    else:
        # Save each date to its own folder
        saved_files = []
        for game_date, stats in games_by_date.items():
            output_dir = f"/Users/CatMurphy/Desktop/GitHub/props/data/box_scores/{game_date}"
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            date_output_file = f"{output_dir}/march_madness_box_scores_{timestamp}.csv"
            
            save_to_csv(date_output_file, {game_date: stats})
            print(f"\nSaved {len(stats)} records to: {date_output_file}")
            saved_files.append(date_output_file)
        
        return saved_files

def save_to_csv(filename, games_by_date):
    """Helper function to save game stats to CSV"""
    with open(filename, 'w', newline='') as f:
        csv_writer = csv.writer(f)
        
        header = [
            'game_id', 'date', 'team_location', 'team_mascot',
            'opponent_location', 'opponent_mascot', 'player_name', 'uniform',
            'minutes', 'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta',
            'points', 'oreb', 'dreb', 'reb', 'ast', 'tov', 'stl', 'blk', 'pf'
        ]
        csv_writer.writerow(header)
        
        for game_date in sorted(games_by_date.keys()):
            for stat_row in games_by_date[game_date]:
                csv_writer.writerow(stat_row)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape March Madness box scores from ESPN')
    parser.add_argument('--dates', nargs='+', required=True, 
                       help='Dates to scrape (YYYYMMDD format). Example: 20260319 20260320')
    parser.add_argument('--output', type=str, 
                       help='Output CSV file path')
    
    args = parser.parse_args()
    
    scrape_march_madness_box_scores(args.dates, args.output)
