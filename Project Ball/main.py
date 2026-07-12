import os
import sys
import database
import api_client
import calculator
from datetime import datetime

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title.center(58)} ")
    print("=" * 60)

def display_menu():
    print_header("SOCCER PREDICTION BOT (CLI)")
    print("1. Sync Standings & Teams (e.g., WC for World Cup, PL for EPL)")
    print("2. Sync Matches (Fetch Upcoming & Finished Matches)")
    print("3. List Matches in Database (Select Match to Predict)")
    print("4. Quick Predict Match by ID")
    print("5. Run All Pending Predictions")
    print("6. Exit")
    print("-" * 60)

def handle_sync_standings():
    print_header("SYNC STANDINGS & TEAMS")
    comp_code = input("Enter competition code (default 'WC' for World Cup, 'PL' for EPL): ").strip().upper()
    if not comp_code:
        comp_code = 'WC'
        
    print(f"Starting sync for {comp_code}...")
    success = api_client.sync_competition_and_teams(comp_code)
    if success:
        print("[SUCCESS] Standings and Teams synchronized successfully.")
    else:
        print("[ERROR] Sync failed. Check your API token or rate limit.")

def handle_sync_matches():
    print_header("SYNC MATCHES")
    comp_code = input("Enter competition code (default 'WC' for World Cup): ").strip().upper()
    if not comp_code:
        comp_code = 'WC'
        
    date_from = input("Start Date (YYYY-MM-DD, optional, e.g. 2026-07-09): ").strip()
    date_to = input("End Date (YYYY-MM-DD, optional, e.g. 2026-07-15): ").strip()
    
    # Defaults for dates if not supplied and not using competition
    if not comp_code and not date_from:
        date_from = datetime.now().strftime("%Y-%m-%d")
        
    print("Syncing matches...")
    matches = api_client.sync_matches(
        comp_code=comp_code if comp_code else None,
        date_from=date_from if date_from else None,
        date_to=date_to if date_to else None
    )
    
    if matches:
        print(f"[SUCCESS] {len(matches)} matches synced and saved to database.")
    else:
        print("[WARNING] No matches returned. You may need to specify correct parameters or token.")

def handle_list_matches():
    print_header("MATCH LIST")
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id, c.code as comp_code, t_home.name as home_name, t_away.name as away_name, 
               m.utc_date, m.status, m.home_score, m.away_score, m.stage
        FROM matches m
        JOIN competitions c ON m.competition_id = c.id
        JOIN teams t_home ON m.home_team_id = t_home.id
        JOIN teams t_away ON m.away_team_id = t_away.id
        ORDER BY m.utc_date ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No matches found in database. Please run Sync Matches first.")
        return
        
    print(f"{'ID':<8} | {'Comp':<5} | {'Home vs Away':<40} | {'Status':<10} | {'Score':<6} | {'Stage':<15}")
    print("-" * 95)
    for r in rows:
        score_str = f"{r['home_score']}-{r['away_score']}" if r['home_score'] is not None else "N/A"
        date_obj = datetime.strptime(r['utc_date'], "%Y-%m-%dT%H:%M:%SZ")
        date_str = date_obj.strftime("%d %b %H:%M")
        match_str = f"{r['home_name']} vs {r['away_name']}"
        print(f"{r['id']:<8} | {r['comp_code']:<5} | {match_str:<40} | {r['status']:<10} | {score_str:<6} | {r['stage'] or 'N/A':<15}")
        
    print("-" * 95)
    match_id_input = input("Enter Match ID to calculate prediction (or press Enter to return): ").strip()
    if match_id_input:
        try:
            match_id = int(match_id_input)
            # Find the comp code for this match
            comp_code = 'WC'
            for r in rows:
                if r['id'] == match_id:
                    comp_code = r['comp_code']
                    break
            run_prediction(match_id, comp_code)
        except ValueError:
            print("[ERROR] Invalid Match ID.")

def handle_quick_predict():
    print_header("QUICK PREDICT")
    try:
        match_id = int(input("Enter Match ID: ").strip())
        comp_code = input("Enter Competition Code (default 'WC'): ").strip().upper()
        if not comp_code:
            comp_code = 'WC'
        run_prediction(match_id, comp_code)
    except ValueError:
        print("[ERROR] Match ID must be an integer.")

def run_prediction(match_id, comp_code):
    try:
        res = calculator.calculate_match_prediction(match_id, comp_code)
        print_header(f"PREDICTION RESULT: {res['home_name']} vs {res['away_name']}")
        print(f"Venue Context  : {'Neutral Ground' if res['is_neutral'] else 'Home Stadium'}")
        print(f"Form Home Team : {res['home_name']} ({res['home_form']})")
        print(f"Form Away Team : {res['away_name']} ({res['away_form']})")
        print(f"Expected Goals : {res['home_name']} ({res['expected_home_goals']}) | {res['away_name']} ({res['expected_away_goals']})")
        print("-" * 60)
        print(">>> MARKET: MONEYLINE (1X2)")
        print(f"  Model Prob   : [HOME: {res['prob_home']}%]  [DRAW: {res['prob_draw']}%]  [AWAY: {res['prob_away']}%]")
        print(f"  Model Odds   : [HOME: {res['odds_home']}]  [DRAW: {res['odds_draw']}]  [AWAY: {res['odds_away']}]")
        
        # Display Polymarket if available
        p = res.get('polymarket')
        if p:
            print(f"  Poly Prob    : [HOME: {p['home_prob']}%]  [DRAW: {p['draw_prob']}%]  [AWAY: {p['away_prob']}%]")
            print(f"  Poly Odds    : [HOME: {p['odds_home']}]  [DRAW: {p['odds_draw']}]  [AWAY: {p['odds_away']}]")
            
            # Value bet detection
            value_bets = []
            if res['odds_home'] < p['odds_home'] and p['odds_home'] < 50.0:
                value_bets.append(f"{res['home_name']} [HOME] (Model: {res['odds_home']} vs Poly: {p['odds_home']})")
            if p['odds_draw'] and res['odds_draw'] < p['odds_draw'] and p['odds_draw'] < 50.0:
                value_bets.append(f"DRAW (Model: {res['odds_draw']} vs Poly: {p['odds_draw']})")
            if p['odds_away'] and res['odds_away'] < p['odds_away'] and p['odds_away'] < 50.0:
                value_bets.append(f"{res['away_name']} [AWAY] (Model: {res['odds_away']} vs Poly: {p['odds_away']})")
                
            if value_bets:
                print("  $$$ RECOMMENDED MONEYLINE BET (VALUE DETECTED):")
                for bet in value_bets:
                    print(f"    -> Taruhan pada: {bet}")
            else:
                print("  No moneyline value bet detected.")
        else:
            print("  Polymarket odds not found for this match.")
            
        print("-" * 60)
        
        # Display To Advance market for knockout matches
        if res.get('is_knockout') and res.get('to_advance'):
            print(">>> MARKET: TO ADVANCE / TO QUALIFY (LOLOS KE BABAK BERIKUTNYA)")
            adv = res['to_advance']
            print(f"  {res['home_name']}: Prob: {adv['prob_home']}% | Odds Wajar: {adv['odds_home']}")
            print(f"  {res['away_name']}: Prob: {adv['prob_away']}% | Odds Wajar: {adv['odds_away']}")
            
            # Display Polymarket "Who will advance" if available
            p = res.get('polymarket')
            if p and p.get('event_title') and 'advance' in p['event_title'].lower():
                print(f"  Poly Prob    : [{res['home_name']}: {p['home_prob']}%]  [{res['away_name']}: {p['away_prob']}%]")
                print(f"  Poly Odds    : [{res['home_name']}: {p['odds_home']}]  [{res['away_name']}: {p['odds_away']}]")
                
                # Value bet detection for To Advance
                adv_value = []
                if adv['odds_home'] < p['odds_home'] and p['odds_home'] < 50.0:
                    adv_value.append(f"{res['home_name']} (Model: {adv['odds_home']} vs Poly: {p['odds_home']})")
                if adv['odds_away'] < p['odds_away'] and p['odds_away'] < 50.0:
                    adv_value.append(f"{res['away_name']} (Model: {adv['odds_away']} vs Poly: {p['odds_away']})")
                    
                if adv_value:
                    print("  $$$ RECOMMENDED TO ADVANCE BET (VALUE DETECTED):")
                    for bet in adv_value:
                        print(f"    -> Taruhan pada: {bet}")
            print("-" * 60)
        print(">>> MARKET: OVER / UNDER 2.5 GOALS")
        ou = res['over_under']
        print(f"  OVER 2.5 Goals : Prob: {ou['prob_over']}% | Odds Wajar: {ou['odds_over']}")
        print(f"  UNDER 2.5 Goals: Prob: {ou['prob_under']}% | Odds Wajar: {ou['odds_under']}")
        if ou['prob_over'] > 55.0:
            print(f"    -> Rekomendasi: OVER 2.5 Goals (Peluang tinggi: {ou['prob_over']}%)")
        elif ou['prob_under'] > 55.0:
            print(f"    -> Rekomendasi: UNDER 2.5 Goals (Peluang tinggi: {ou['prob_under']}%)")
            
        print("-" * 60)
        print(">>> MARKET: BOTH TEAMS TO SCORE (BTTS)")
        b = res['btts']
        print(f"  BTTS - YES (Kedua tim gol): Prob: {b['prob_yes']}% | Odds Wajar: {b['odds_yes']}")
        print(f"  BTTS - NO  (Salah satu/tidak gol): Prob: {b['prob_no']}% | Odds Wajar: {b['odds_no']}")
        if b['prob_yes'] > 55.0:
            print(f"    -> Rekomendasi: BTTS - YES (Peluang tinggi: {b['prob_yes']}%)")
        elif b['prob_no'] > 55.0:
            print(f"    -> Rekomendasi: BTTS - NO (Peluang tinggi: {b['prob_no']}%)")
            
        print("-" * 60)
        print(">>> MARKET: TOP 3 CORRECT SCORE (TEBAK SKOR)")
        for idx, item in enumerate(res['top_scores'], 1):
            h_score, a_score = item['score'].split('-')
            score_desc = f"{res['home_name']} {h_score} - {a_score} {res['away_name']}"
            print(f"  {idx}. Skor [{score_desc}]: Prob: {item['prob']}% | Odds Wajar: {item['odds']}")
            
        print("-" * 60)
        if res['h2h_used']:
            print(f"H2H Stats Used : Yes (based on {res['h2h_matches']} recent matches)")
        else:
            print("H2H Stats Used : No (insufficient historical data)")
        print("=" * 60)
    except Exception as e:
        print(f"[ERROR] Calculation failed: {e}")

def handle_predict_all():
    print_header("RUNNING ALL PENDING PREDICTIONS")
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id, c.code as comp_code
        FROM matches m
        JOIN competitions c ON m.competition_id = c.id
        WHERE m.status = 'SCHEDULED' OR m.status = 'TIMED'
        """
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No upcoming/scheduled matches found in database.")
        return
        
    print(f"Found {len(rows)} scheduled matches. Processing calculations...")
    success_count = 0
    for r in rows:
        try:
            calculator.calculate_match_prediction(r['id'], r['comp_code'])
            success_count += 1
        except Exception as e:
            pass
            
    print(f"[SUCCESS] Calculated {success_count}/{len(rows)} predictions.")

def main():
    database.init_db()
    
    # Auto-detect if user wants to run direct CLI options
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "sync":
            api_client.sync_competition_and_teams("WC")
            api_client.sync_matches("WC")
            print("Auto-sync World Cup complete.")
            return
            
    while True:
        display_menu()
        choice = input("Enter your choice (1-6): ").strip()
        if choice == '1':
            handle_sync_standings()
        elif choice == '2':
            handle_sync_matches()
        elif choice == '3':
            handle_list_matches()
        elif choice == '4':
            handle_quick_predict()
        elif choice == '5':
            handle_predict_all()
        elif choice == '6':
            print("Goodbye!")
            break
        else:
            print("[ERROR] Invalid choice. Please select between 1 and 6.")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()
