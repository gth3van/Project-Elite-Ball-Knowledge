import os
import sys
import database
import api_client
import calculator
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

MENU_COMPS = {
    "PD":  "La Liga",
    "CL":  "UEFA Champions League",
    "PL":  "Premier League",
    "BL1": "Bundesliga",
    "SA":  "Serie A",
    "FL1": "Ligue 1",
    "WC":  "FIFA World Cup",
    "EC":  "Euros",
}


def print_header(title):
    print("\n" + "=" * 64)
    print(f"  {title.center(60)}  ")
    print("=" * 64)


def print_sep():
    print("-" * 64)


def display_menu():
    print_header("WeBallinGang  --  Sportsbook Analyst CLI")
    print("  1. Sync Standings + Matches  (single competition)")
    print("  2. Quick Sync ALL Active Competitions")
    print("  3. Sync by Date Range  (e.g. Friendlies)")
    print("  4. List Matches + Predict")
    print("  5. Quick Predict by Match ID")
    print("  6. Run All Scheduled Predictions")
    print("  7. *** BEST BET SCANNER ***")
    print("  8. Exit")
    print_sep()


# --------------------------------------------------------------------------- #
#  Sync handlers                                                                #
# --------------------------------------------------------------------------- #

def handle_sync_single():
    print_header("SYNC -- Single Competition")
    for code, name in MENU_COMPS.items():
        print(f"  {code:<5} = {name}")
    print_sep()
    comp_code = input("Competition code: ").strip().upper()
    if not comp_code:
        print("[ERROR] No code entered.")
        return
    api_client.sync_competition_and_teams(comp_code)
    api_client.sync_matches(comp_code=comp_code)
    print("[SUCCESS] Sync complete.")


def handle_sync_all():
    print_header("QUICK SYNC -- All Active Competitions")
    confirm = input("Sync PD, CL, PL, BL1, SA, FL1? (y/n): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return
    results = api_client.sync_all_active()
    for code, count in results.items():
        print(f"  {code:<5} {MENU_COMPS.get(code, code):<30} {count} matches")
    print("[SUCCESS] Done.")


def handle_sync_date_range():
    print_header("SYNC -- By Date Range")
    date_from = input("Start date (YYYY-MM-DD): ").strip()
    date_to   = input("End date   (YYYY-MM-DD): ").strip()
    comp_code = input("Competition code (blank = all): ").strip().upper()
    api_client.sync_matches(
        comp_code=comp_code or None,
        date_from=date_from or None,
        date_to=date_to or None
    )
    print("[SUCCESS] Done.")


# --------------------------------------------------------------------------- #
#  Match list + predict                                                         #
# --------------------------------------------------------------------------- #

def handle_list_matches():
    print_header("MATCH LIST")
    for code, name in MENU_COMPS.items():
        print(f"  {code:<5} = {name}")
    print_sep()
    filter_code = input("Filter by comp code (or Enter for all): ").strip().upper()

    conn = database.get_connection()
    cur  = conn.cursor()
    if filter_code:
        cur.execute(
            """
            SELECT m.id, c.code as comp_code, t_home.name as home_name,
                   t_away.name as away_name, m.utc_date, m.status,
                   m.home_score, m.away_score, m.stage
            FROM matches m
            JOIN competitions c ON m.competition_id = c.id
            JOIN teams t_home ON m.home_team_id = t_home.id
            JOIN teams t_away ON m.away_team_id = t_away.id
            WHERE c.code = ? ORDER BY m.utc_date ASC
            """, (filter_code,)
        )
    else:
        cur.execute(
            """
            SELECT m.id, c.code as comp_code, t_home.name as home_name,
                   t_away.name as away_name, m.utc_date, m.status,
                   m.home_score, m.away_score, m.stage
            FROM matches m
            JOIN competitions c ON m.competition_id = c.id
            JOIN teams t_home ON m.home_team_id = t_home.id
            JOIN teams t_away ON m.away_team_id = t_away.id
            ORDER BY m.utc_date ASC
            """
        )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No matches found. Run a sync first.")
        return

    print(f"\n{'ID':<9} {'Comp':<5} {'Home vs Away':<40} {'Status':<11} {'Score':<7} Date (WIB)")
    print_sep()
    for r in rows:
        score_str = f"{r['home_score']}-{r['away_score']}" if r['home_score'] is not None else "---"
        try:
            utc_dt  = datetime.strptime(r['utc_date'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            wib_str = utc_dt.astimezone(WIB).strftime("%d %b %H:%M WIB")
        except Exception:
            wib_str = r['utc_date']
        match_str = f"{r['home_name']} vs {r['away_name']}"
        print(f"{r['id']:<9} {r['comp_code']:<5} {match_str:<40} {r['status']:<11} {score_str:<7} {wib_str}")

    print_sep()
    mid = input("Match ID to predict (or Enter to return): ").strip()
    if mid:
        try:
            run_prediction(int(mid))
        except ValueError:
            print("[ERROR] Invalid ID.")


def handle_quick_predict():
    print_header("QUICK PREDICT")
    try:
        match_id = int(input("Match ID: ").strip())
        run_prediction(match_id)
    except ValueError:
        print("[ERROR] Match ID must be an integer.")


def handle_predict_all():
    print_header("RUN ALL PENDING PREDICTIONS")
    conn = database.get_connection()
    cur  = conn.cursor()
    cur.execute(
        """
        SELECT m.id, c.code as comp_code FROM matches m
        JOIN competitions c ON m.competition_id = c.id
        WHERE m.status IN ('SCHEDULED', 'TIMED')
        """
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No upcoming matches. Run sync first.")
        return
    ok = 0
    for r in rows:
        try:
            calculator.calculate_match_prediction(r['id'], r['comp_code'])
            ok += 1
        except Exception as e:
            print(f"  [SKIP] {r['id']}: {e}")
    print(f"[SUCCESS] {ok}/{len(rows)} predictions done.")


# --------------------------------------------------------------------------- #
#  BEST BET SCANNER                                                             #
# --------------------------------------------------------------------------- #

def _extract_bets(res):
    """
    Flatten all betting markets from one prediction result into a list of
    bet-candidate dicts, each scored by:
      - edge_pct  if Polymarket odds are available and > fair odds
      - prob      otherwise (model confidence)
    """
    home  = res['home_name']
    away  = res['away_name']
    label = f"{home} vs {away}"
    poly  = res.get('polymarket')
    bets  = []

    def add(market, prob, poly_odds=None):
        fair = round(100.0 / prob, 2) if prob > 0 else 99.0
        edge = None
        if poly_odds and 0 < poly_odds < 50.0:
            edge = round((poly_odds / fair - 1) * 100, 1)
        bets.append({
            "match":     label,
            "market":    market,
            "prob":      prob,
            "fair_odds": fair,
            "poly_odds": poly_odds,
            "edge_pct":  edge,
            "has_value": edge is not None and edge > 0,
        })

    # 1X2
    ph = poly['odds_home'] if poly else None
    pd = poly['odds_draw'] if poly else None
    pa = poly['odds_away'] if poly else None
    add("HOME WIN",  res['prob_home'], ph)
    add("DRAW",      res['prob_draw'], pd)
    add("AWAY WIN",  res['prob_away'], pa)

    # Over/Under + BTTS (model-only, Polymarket rarely has these)
    add("OVER 2.5",  res['over_under']['prob_over'])
    add("UNDER 2.5", res['over_under']['prob_under'])
    add("BTTS YES",  res['btts']['prob_yes'])
    add("BTTS NO",   res['btts']['prob_no'])

    # To Advance (knockout stage)
    if res.get('is_knockout') and res.get('to_advance'):
        adv = res['to_advance']
        add(f"ADVANCE {home[:14]}", adv['prob_home'])
        add(f"ADVANCE {away[:14]}", adv['prob_away'])

    return bets


def handle_best_bet_scanner():
    print_header("*** BEST BET SCANNER ***")
    print("Ranks bets by:")
    print("  [1] EDGE %          (Polymarket odds > fair odds)  <- primary")
    print("  [2] CONFIDENCE %    (model probability)            <- fallback")
    print_sep()

    print("Scope:")
    print("  a) All scheduled matches")
    print("  b) Filter by competition")
    print("  c) Single match ID")
    scope = input("Choice (a/b/c): ").strip().lower()

    conn = database.get_connection()
    cur  = conn.cursor()

    if scope == "c":
        mid = input("Match ID: ").strip()
        cur.execute(
            """
            SELECT m.id, c.code as comp_code, c.name as comp_name
            FROM matches m JOIN competitions c ON m.competition_id = c.id
            WHERE m.id = ?
            """, (mid,)
        )
    elif scope == "b":
        for code, name in MENU_COMPS.items():
            print(f"  {code} = {name}")
        fc = input("Competition code: ").strip().upper()
        cur.execute(
            """
            SELECT m.id, c.code as comp_code, c.name as comp_name
            FROM matches m JOIN competitions c ON m.competition_id = c.id
            WHERE m.status IN ('SCHEDULED','TIMED') AND c.code = ?
            ORDER BY m.utc_date ASC
            """, (fc,)
        )
    else:
        cur.execute(
            """
            SELECT m.id, c.code as comp_code, c.name as comp_name
            FROM matches m JOIN competitions c ON m.competition_id = c.id
            WHERE m.status IN ('SCHEDULED','TIMED')
            ORDER BY m.utc_date ASC
            """
        )

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No matches found. Sync first.")
        return

    print(f"\n  Scanning {len(rows)} match(es) -- please wait...\n")
    all_bets = []
    for r in rows:
        try:
            res  = calculator.calculate_match_prediction(r['id'], r['comp_code'])
            bets = _extract_bets(res)
            all_bets.extend(bets)
        except Exception as e:
            print(f"  [SKIP] Match {r['id']}: {e}")

    if not all_bets:
        print("No bets generated.")
        return

    # ── Section 1: Value Bets (Polymarket edge > 0) ─────────────────────
    value_bets = sorted(
        [b for b in all_bets if b['has_value']],
        key=lambda x: x['edge_pct'], reverse=True
    )

    print_header("[1] VALUE BETS  (Polymarket odds > fair odds)")
    if value_bets:
        print(f"  {'Match':<33} {'Market':<20} {'Prob':>6}  {'Fair':>5}  {'Poly':>5}  {'Edge':>7}")
        print_sep()
        for b in value_bets[:10]:
            print(
                f"  {b['match'][:32]:<33} {b['market']:<20}"
                f" {b['prob']:>5.1f}%  {b['fair_odds']:>5.2f}"
                f"  {b['poly_odds']:>5.2f}  +{b['edge_pct']:>5.1f}%"
            )
        if len(value_bets) > 10:
            print(f"  ... and {len(value_bets)-10} more value bets.")
    else:
        print("  No Polymarket value bets found.")
        print("  (Markets may not be open yet for upcoming fixtures.)")

    # ── Section 2: High-Confidence Model Bets ───────────────────────────
    strong = sorted(
        [b for b in all_bets if b['prob'] >= 65.0],
        key=lambda x: x['prob'], reverse=True
    )

    print_header("[2] HIGH-CONFIDENCE MODEL BETS  (>= 65% probability)")
    display_bets = strong[:10] if strong else sorted(all_bets, key=lambda x: x['prob'], reverse=True)[:5]
    if display_bets:
        if not strong:
            print("  (None >= 65%. Showing top 5 instead.)")
        print(f"  {'Match':<33} {'Market':<20} {'Prob':>7}  {'Fair Odds':>9}  Confidence")
        print_sep()
        for b in display_bets:
            filled = int(b['prob'] / 5)
            bar    = "[" + "#" * filled + "-" * (20 - filled) + "]"
            print(f"  {b['match'][:32]:<33} {b['market']:<20} {b['prob']:>6.1f}%  {b['fair_odds']:>9.2f}  {bar}")

    print_sep()
    print("  TIP: Best picks = high confidence + positive Polymarket edge.")
    print("=" * 64 + "\n")


# --------------------------------------------------------------------------- #
#  Prediction display                                                           #
# --------------------------------------------------------------------------- #

def run_prediction(match_id):
    conn = database.get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT c.code FROM matches m JOIN competitions c ON m.competition_id=c.id WHERE m.id=?",
        (match_id,)
    )
    row = cur.fetchone()
    conn.close()
    comp_code = row['code'] if row else 'UNK'
    try:
        res = calculator.calculate_match_prediction(match_id, comp_code)
        display_prediction(res)
    except Exception as e:
        print(f"[ERROR] {e}")


def _vtag(prob, poly_odds):
    if poly_odds and 0 < poly_odds < 50.0:
        fair = round(100.0 / prob, 2) if prob > 0 else 99.0
        if poly_odds > fair:
            edge = round((poly_odds / fair - 1) * 100, 1)
            return f"  >>> VALUE BET!  Market: {poly_odds}  |  Fair: {fair}  |  Edge: +{edge}%"
    return ""


def display_prediction(res):
    home = res['home_name']
    away = res['away_name']
    poly = res.get('polymarket')

    print_header(f"PREDICTION: {home} vs {away}")
    print(f"  Venue : {'Neutral' if res['is_neutral'] else 'Home Advantage'}")
    print(f"  Form  {home[:16]:<16}: {res['home_form']}")
    print(f"  Form  {away[:16]:<16}: {res['away_form']}")
    print(f"  xG    : {home} ({res['expected_home_goals']})  |  {away} ({res['expected_away_goals']})")
    print_sep()

    print(">>> MONEYLINE (1X2)")
    print(f"  Model : HOME {res['prob_home']}%  DRAW {res['prob_draw']}%  AWAY {res['prob_away']}%")
    print(f"  Odds  : HOME {res['odds_home']}   DRAW {res['odds_draw']}   AWAY {res['odds_away']}")
    if poly:
        print(f"  Poly  : HOME {poly['odds_home']} ({poly['home_prob']}%)  "
              f"DRAW {poly['odds_draw']} ({poly['draw_prob']}%)  "
              f"AWAY {poly['odds_away']} ({poly['away_prob']}%)")
        print(f"  Src   : {poly.get('event_title', 'N/A')}")
        for tag in [_vtag(res['prob_home'], poly['odds_home']),
                    _vtag(res['prob_draw'], poly['odds_draw']),
                    _vtag(res['prob_away'], poly['odds_away'])]:
            if tag:
                print(tag)
    else:
        print("  Poly  : No market found.")
    print_sep()

    if res.get('is_knockout') and res.get('to_advance'):
        adv = res['to_advance']
        print(">>> TO ADVANCE  (incl. OT + Penalties)")
        print(f"  {home:<30}: {adv['prob_home']}%  Odds: {adv['odds_home']}")
        print(f"  {away:<30}: {adv['prob_away']}%  Odds: {adv['odds_away']}")
        print_sep()

    ou = res['over_under']
    print(">>> OVER / UNDER 2.5 GOALS")
    print(f"  OVER  2.5: {ou['prob_over']}%  Odds: {ou['odds_over']}")
    print(f"  UNDER 2.5: {ou['prob_under']}%  Odds: {ou['odds_under']}")
    rec = "OVER 2.5" if ou['prob_over'] > ou['prob_under'] else "UNDER 2.5"
    print(f"  -> Rec: {rec} ({max(ou['prob_over'], ou['prob_under'])}%)")
    print_sep()

    bt = res['btts']
    print(">>> BOTH TEAMS TO SCORE (BTTS)")
    print(f"  YES: {bt['prob_yes']}%  Odds: {bt['odds_yes']}")
    print(f"  NO : {bt['prob_no']}%  Odds: {bt['odds_no']}")
    rec_bt = "BTTS YES" if bt['prob_yes'] > bt['prob_no'] else "BTTS NO"
    print(f"  -> Rec: {rec_bt} ({max(bt['prob_yes'], bt['prob_no'])}%)")
    print_sep()

    print(">>> TOP 3 CORRECT SCORE")
    for i, s in enumerate(res['top_scores'], 1):
        print(f"  {i}. {s['score']:<48} {s['prob']}%  Odds: {s['odds']}")
    print_sep()

    h2h_note = (f"H2H applied ({res['h2h_matches']} matches, 25% weight)."
                if res['h2h_used'] else "H2H not applied.")
    print(f"  {h2h_note}")
    print("=" * 64 + "\n")


# --------------------------------------------------------------------------- #
#  Main loop                                                                    #
# --------------------------------------------------------------------------- #

def main():
    database.init_db()

    # CLI shortcuts: python main.py sync PD | syncall | bestbets
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "sync" and len(sys.argv) > 2:
            code = sys.argv[2].upper()
            api_client.sync_competition_and_teams(code)
            api_client.sync_matches(comp_code=code)
            return
        elif cmd == "syncall":
            api_client.sync_all_active()
            return
        elif cmd == "bestbets":
            handle_best_bet_scanner()
            return

    while True:
        display_menu()
        choice = input("Your choice (1-8): ").strip()

        if   choice == '1': handle_sync_single()
        elif choice == '2': handle_sync_all()
        elif choice == '3': handle_sync_date_range()
        elif choice == '4': handle_list_matches()
        elif choice == '5': handle_quick_predict()
        elif choice == '6': handle_predict_all()
        elif choice == '7': handle_best_bet_scanner()
        elif choice == '8':
            print("\nGoodbye! Stay sharp.")
            break
        else:
            print("[ERROR] Enter 1-8.")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
