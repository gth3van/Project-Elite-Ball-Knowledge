import os
import time
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

# Supported competitions with human-readable names
SUPPORTED_COMPETITIONS = {
    "WC":  "FIFA World Cup",
    "CL":  "UEFA Champions League",
    "PD":  "La Liga",
    "PL":  "Premier League",
    "BL1": "Bundesliga",
    "SA":  "Serie A",
    "FL1": "Ligue 1",
    "PPL": "Primeira Liga",
    "EC":  "European Championship",
    "DED": "Eredivisie",
}

def get_from_api(endpoint, params=None, retry_on_limit=True):
    """
    Fetch data from the Football Data API with automatic rate-limit handling.
    If a 429 is received, waits 61 seconds and retries once.
    """
    if not API_TOKEN:
        raise ValueError("API Token not found! Please set FOOTBALL_API_TOKEN in the .env file.")

    url = f"{BASE_URL}/{endpoint}"
    response = requests.get(url, headers=headers, params=params, timeout=15)

    if response.status_code == 429:
        if retry_on_limit:
            print("[WARNING] API Rate Limit hit (10 req/min). Auto-waiting 61 seconds...")
            time.sleep(61)
            return get_from_api(endpoint, params=params, retry_on_limit=False)
        else:
            print("[ERROR] Rate limit hit again after waiting. Try again later.")
            return None
    elif response.status_code == 403:
        print(f"[ERROR] Access denied (403). This competition may need a paid API tier.")
        return None
    elif response.status_code != 200:
        print(f"[ERROR] API request failed ({response.status_code}): {response.text[:200]}")
        return None

    return response.json()


def sync_competition_and_teams(comp_code):
    """Fetch standings and sync competitions/teams/standings tables."""
    comp_name = SUPPORTED_COMPETITIONS.get(comp_code, comp_code)
    print(f"  Syncing standings for: {comp_name} ({comp_code})...")
    data = get_from_api(f"competitions/{comp_code}/standings")
    if not data:
        return False

    comp_id = data['competition']['id']
    comp_name = data['competition']['name']
    database.save_competition(comp_id, comp_code, comp_name)

    standings_list = data.get('standings', [])
    for standing in standings_list:
        if standing.get('type') == 'TOTAL':
            table = standing.get('table', [])
            for row in table:
                team = row['team']
                team_id = team['id']
                database.save_team(team_id, team['name'], team.get('shortName'), team.get('tla'))
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
    print(f"  [OK] Standings synced: {comp_name}")
    return True


def sync_matches(comp_code=None, date_from=None, date_to=None):
    """Sync matches for a competition or a date range."""
    params = {}
    if date_from:
        params['dateFrom'] = date_from
    if date_to:
        params['dateTo'] = date_to

    if comp_code:
        print(f"  Syncing matches for: {SUPPORTED_COMPETITIONS.get(comp_code, comp_code)} ({comp_code})...")
        endpoint = f"competitions/{comp_code}/matches"
    else:
        print("  Syncing matches for date range...")
        endpoint = "matches"

    data = get_from_api(endpoint, params=params)
    if not data:
        return []

    matches = data.get('matches', [])
    print(f"  Found {len(matches)} matches. Saving to database...")

    saved = 0
    for match in matches:
        comp = match['competition']
        database.save_competition(comp['id'], comp['code'], comp['name'])

        home = match['homeTeam']
        away = match['awayTeam']

        if not home.get('id') or not away.get('id'):
            continue

        database.save_team(home['id'], home.get('name', 'TBD'), home.get('shortName'), home.get('tla'))
        database.save_team(away['id'], away.get('name', 'TBD'), away.get('shortName'), away.get('tla'))

        score = match.get('score', {})
        full_time = score.get('fullTime', {})

        database.save_match(
            id=match['id'],
            competition_id=comp['id'],
            home_team_id=home['id'],
            away_team_id=away['id'],
            utc_date=match['utcDate'],
            status=match['status'],
            home_score=full_time.get('home'),
            away_score=full_time.get('away'),
            matchday=match.get('matchday'),
            stage=match.get('stage')
        )
        saved += 1

    print(f"  [OK] Saved {saved} matches.")
    return matches


def sync_all_active(date_from=None, date_to=None):
    """
    Sync matches for all currently active club competitions at once.
    Returns dict {comp_code: match_count}.
    """
    active_comps = ["PD", "CL", "PL", "BL1", "SA", "FL1"]
    results = {}
    for code in active_comps:
        print(f"\n[{code}] {SUPPORTED_COMPETITIONS.get(code, code)}")
        sync_competition_and_teams(code)
        matches = sync_matches(comp_code=code, date_from=date_from, date_to=date_to)
        results[code] = len(matches)
    return results


def get_match_h2h(match_id):
    """Fetch Head-to-Head data for a specific match."""
    print(f"  Fetching H2H data for match {match_id}...")
    data = get_from_api(f"matches/{match_id}/head2head")
    return data


def get_polymarket_odds(home_team, away_team, comp_code=None):
    """
    Search and fetch real-time odds from Polymarket Gamma API.
    Supports filtering by competition type to avoid cross-league market mixing.
    """
    print(f"  Searching Polymarket: {home_team} vs {away_team} [{comp_code}]...")
    url = "https://gamma-api.polymarket.com/public-search"

    COMP_KEYWORDS = {
        "WC":  ["world cup", "fifa", "world"],
        "CL":  ["champions league", "ucl", "uefa champions"],
        "EC":  ["euro", "european championship", "uefa euro"],
        "PL":  ["premier league", "epl"],
        "PD":  ["la liga", "laliga", "spanish"],
        "BL1": ["bundesliga", "german"],
        "SA":  ["serie a", "italian"],
        "FL1": ["ligue 1", "ligue1", "french"],
        "INT": ["friendly", "international", "nations league"],
    }
    filter_keywords = COMP_KEYWORDS.get(comp_code, []) if comp_code else []
    MAX_LIVE_ODDS = 50.0

    for q_term in [home_team, away_team]:
        try:
            res = requests.get(url, params={'q': q_term}, timeout=10)
            if res.status_code != 200:
                continue

            events = res.json().get('events', [])

            for e in events:
                title = e.get('title', '').lower()
                if home_team.lower() not in title or away_team.lower() not in title:
                    continue
                if filter_keywords and not any(kw in title for kw in filter_keywords):
                    continue

                markets = e.get('markets', [])
                home_p = draw_p = away_p = None

                for m in markets:
                    if not m.get('active') or not m.get('outcomePrices'):
                        continue

                    q_text = m.get('question', '').lower()
                    raw_prices = m.get('outcomePrices')

                    if isinstance(raw_prices, str):
                        try:
                            prices = json.loads(raw_prices)
                        except Exception:
                            continue
                    else:
                        prices = raw_prices

                    if not prices or len(prices) < 2:
                        continue

                    try:
                        yes_price = float(prices[0])
                    except (ValueError, TypeError):
                        continue

                    # Skip already-settled markets
                    if yes_price > 0 and (1.0 / yes_price) >= MAX_LIVE_ODDS:
                        continue

                    # Parse team-name outcomes array
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

                    h_low = home_team.lower()
                    a_low = away_team.lower()

                    if outcomes and len(outcomes) == 2 and len(prices) == 2:
                        out_0 = outcomes[0].lower()
                        out_1 = outcomes[1].lower()
                        try:
                            p0, p1 = float(prices[0]), float(prices[1])
                        except (ValueError, TypeError):
                            continue
                        if out_0 == h_low and out_1 == a_low:
                            home_p, away_p = p0, p1
                        elif out_0 == a_low and out_1 == h_low:
                            away_p, home_p = p0, p1
                    elif 'draw' in q_text:
                        draw_p = yes_price
                    elif q_text.startswith(f"will {h_low}"):
                        home_p = yes_price
                    elif q_text.startswith(f"will {a_low}"):
                        away_p = yes_price

                if home_p is not None:
                    def safe_odds(p):
                        return round(1.0 / p, 2) if (p and p > 0) else 99.0

                    return {
                        'home_prob': round(home_p * 100, 1),
                        'draw_prob': round(draw_p * 100, 1) if draw_p else 0.0,
                        'away_prob': round(away_p * 100, 1) if away_p else 0.0,
                        'odds_home': safe_odds(home_p),
                        'odds_draw': safe_odds(draw_p),
                        'odds_away': safe_odds(away_p),
                        'event_title': e.get('title')
                    }

        except Exception as err:
            print(f"  [WARNING] Polymarket fetch error: {err}")

    return None
