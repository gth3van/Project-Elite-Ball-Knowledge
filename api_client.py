import os
import requests
import json
from dotenv import load_dotenv
import database

# Load environment variables
load_dotenv()

API_TOKEN = os.getenv("FOOTBALL_API_TOKEN")
BASE_URL = "https://api.football-data.org/v4"

headers = {
    "X-Auth-Token": API_TOKEN
}

def get_from_api(endpoint, params=None):
    if not API_TOKEN:
        raise ValueError("API Token not found! Please set FOOTBALL_API_TOKEN in the .env file.")
    
    url = f"{BASE_URL}/{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 429:
        print("[WARNING] API Rate Limit Exceeded (10 requests/min). Please wait a moment...")
        return None
    elif response.status_code != 200:
        print(f"[ERROR] API request failed with status code {response.status_code}: {response.text}")
        return None
        
    return response.json()

def sync_competition_and_teams(comp_code):
    """Fetch standings and sync competitions/teams/standings tables"""
    print(f"Syncing standings and teams for competition: {comp_code}...")
    data = get_from_api(f"competitions/{comp_code}/standings")
    if not data:
        return False
    
    # Save competition
    comp_id = data['competition']['id']
    comp_name = data['competition']['name']
    database.save_competition(comp_id, comp_code, comp_name)
    
    # Save teams and standings
    standings_list = data.get('standings', [])
    for standing in standings_list:
        if standing.get('type') == 'TOTAL':
            table = standing.get('table', [])
            for row in table:
                team = row['team']
                team_id = team['id']
                team_name = team['name']
                team_short = team.get('shortName')
                team_tla = team.get('tla')
                
                # Save team
                database.save_team(team_id, team_name, team_short, team_tla)
                
                # Save standings row
                database.save_standing(
                    competition_id=comp_id,
                    team_id=team_id,
                    position=row['position'],
                    played_games=row['playedGames'],
                    won=row['won'],
                    draw=row['draw'],
                    lost=row['lost'],
                    points=row['points'],
                    goals_for=row['goalsFor'],
                    goals_against=row['goalsAgainst']
                )
    print("Sync complete.")
    return True

def sync_matches(comp_code=None, date_from=None, date_to=None):
    """Sync matches for a competition or general date range"""
    params = {}
    if date_from:
        params['dateFrom'] = date_from
    if date_to:
        params['dateTo'] = date_to
        
    if comp_code:
        print(f"Syncing matches for competition: {comp_code}...")
        endpoint = f"competitions/{comp_code}/matches"
    else:
        print("Syncing matches for date range...")
        endpoint = "matches"
        
    data = get_from_api(endpoint, params=params)
    if not data:
        return []
    
    # Save competition if it comes from matches endpoint
    matches = data.get('matches', [])
    print(f"Found {len(matches)} matches. Saving to database...")
    
    for match in matches:
        comp = match['competition']
        database.save_competition(comp['id'], comp['code'], comp['name'])
        
        # Home team
        home = match['homeTeam']
        if home.get('id'):
            database.save_team(home['id'], home['name'], home.get('shortName'), home.get('tla'))
            
        # Away team
        away = match['awayTeam']
        if away.get('id'):
            database.save_team(away['id'], away['name'], away.get('shortName'), away.get('tla'))
            
        # Score
        score = match.get('score', {})
        full_time = score.get('fullTime', {})
        home_score = full_time.get('home')
        away_score = full_time.get('away')
        
        # Save match
        database.save_match(
            id=match['id'],
            competition_id=comp['id'],
            home_team_id=home['id'],
            away_team_id=away['id'],
            utc_date=match['utcDate'],
            status=match['status'],
            home_score=home_score,
            away_score=away_score,
            matchday=match.get('matchday'),
            stage=match.get('stage')
        )
        
    return matches

def get_match_h2h(match_id):
    """Fetch Head-to-Head data for a specific match"""
    print(f"Fetching H2H stats for match ID {match_id}...")
    data = get_from_api(f"matches/{match_id}/head2head")
    return data

def get_polymarket_odds(home_team, away_team, comp_code=None):
    """
    Search and fetch real-time odds/probabilities from Polymarket Gamma API.
    Converts outcome prices to decimal odds.
    """
    print(f"Searching Polymarket for: {home_team} vs {away_team} (Comp: {comp_code})...")
    url = "https://gamma-api.polymarket.com/public-search"
    
    # Try searching for home team first, then away team
    for q_term in [home_team, away_team]:
        try:
            res = requests.get(url, params={'q': q_term}, timeout=10)
            if res.status_code != 200:
                continue
            events = res.json().get('events', [])
            
            for e in events:
                title = e.get('title', '').lower()
                # Check if both teams are mentioned in the event title
                if home_team.lower() in title and away_team.lower() in title:
                    # Filter by competition if provided to prevent cross-league mismatch
                    if comp_code == 'WC' and not ('world cup' in title or 'world' in title or 'fifa' in title):
                        continue
                    if comp_code == 'CL' and not ('champions league' in title or 'uefa' in title):
                        continue
                    
                    markets = e.get('markets', [])
                    home_p = None
                    draw_p = None
                    away_p = None
                    
                    for m in markets:
                        if not m.get('active') or not m.get('outcomePrices'):
                            continue
                        q_text = m.get('question', '').lower()
                        raw_prices = m.get('outcomePrices')
                        
                        if isinstance(raw_prices, str):
                            prices = json.loads(raw_prices)
                        else:
                            prices = raw_prices
                            
                        if not prices or len(prices) < 2:
                            continue
                            
                        try:
                            yes_price = float(prices[0])
                        except ValueError:
                            continue
                            
                        # Parse outcomes to see if they list team names directly (e.g. ["Spain", "France"])
                        raw_outcomes = m.get('outcomes')
                        outcomes = []
                        if raw_outcomes:
                            if isinstance(raw_outcomes, str):
                                try:
                                    outcomes = json.loads(raw_outcomes)
                                except Exception:
                                    pass
                            else:
                                outcomes = raw_outcomes
                                
                        # Classify market type based on question keywords or direct outcome names
                        if outcomes and len(outcomes) == 2 and len(prices) == 2:
                            out_0 = outcomes[0].lower()
                            out_1 = outcomes[1].lower()
                            h_low = home_team.lower()
                            a_low = away_team.lower()
                            if out_0 == h_low and out_1 == a_low:
                                home_p = float(prices[0])
                                away_p = float(prices[1])
                            elif out_0 == a_low and out_1 == h_low:
                                away_p = float(prices[0])
                                home_p = float(prices[1])
                        elif 'draw' in q_text:
                            draw_p = yes_price
                        elif q_text.startswith(f"will {home_team.lower()}"):
                            home_p = yes_price
                        elif q_text.startswith(f"will {away_team.lower()}"):
                            away_p = yes_price
                            
                    if home_p is not None:
                        odds_h = round(1.0 / home_p, 2) if home_p > 0 else 99.0
                        odds_d = round(1.0 / draw_p, 2) if (draw_p and draw_p > 0) else 99.0
                        odds_a = round(1.0 / away_p, 2) if (away_p and away_p > 0) else 99.0
                        return {
                            'home_prob': round(home_p * 100, 1),
                            'draw_prob': round(draw_p * 100, 1) if draw_p else 0.0,
                            'away_prob': round(away_p * 100, 1) if away_p else 0.0,
                            'odds_home': odds_h,
                            'odds_draw': odds_d,
                            'odds_away': odds_a,
                            'event_title': e.get('title')
                        }
        except Exception as err:
            print(f"[WARNING] Polymarket fetch failed: {err}")
            
    return None
