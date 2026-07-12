import math
import database
import api_client

def poisson_probability(lmbda, k):
    """Calculates Poisson probability for scoring k goals given a mean of lmbda."""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def get_team_stats(team_id, competition_id):
    """
    Get team statistics (played, goals_for, goals_against) by aggregating
    all finished matches in the database for this competition.
    This ensures knockout matches are included, unlike static group standings.
    """
    # Calculate directly from matches in DB to include knockout games
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            COUNT(*) as played,
            SUM(CASE WHEN home_team_id = ? THEN home_score ELSE away_score END) as goals_for,
            SUM(CASE WHEN home_team_id = ? THEN away_score ELSE home_score END) as goals_against
        FROM matches
        WHERE (home_team_id = ? OR away_team_id = ?) AND status = 'FINISHED' AND competition_id = ?
        """,
        (team_id, team_id, team_id, team_id, competition_id)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row and row["played"] > 0:
        return {
            "played": row["played"],
            "goals_for": row["goals_for"] or 0,
            "goals_against": row["goals_against"] or 0
        }
    
    # Fallback to standings table if no finished matches are found in DB yet
    stats = database.get_team_stats_from_db(team_id, competition_id)
    if stats:
        return {
            "played": stats["played_games"],
            "goals_for": stats["goals_for"],
            "goals_against": stats["goals_against"]
        }
    
    # Default stats if nothing found
    return {
        "played": 0,
        "goals_for": 0,
        "goals_against": 0
    }

def get_league_average_goals(competition_id):
    """Calculates average goals scored per match in a competition."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT AVG(home_score + away_score) as avg_goals 
        FROM matches 
        WHERE competition_id = ? AND status = 'FINISHED'
        """,
        (competition_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row and row["avg_goals"] is not None:
        # Each team scores half of the match goals on average
        return row["avg_goals"] / 2.0
    
    # Default global average (around 1.35 goals per team per match)
    return 1.35

def get_team_form_modifier(team_id, limit=5):
    """
    Calculate team form modifier based on recent matches with weights
    to prioritize the latest trend (momentum/hot streaks).
    Win = 3 pts, Draw = 1 pt, Loss = 0 pts.
    """
    recent = database.get_team_recent_matches(team_id, limit)
    if not recent:
        return 1.0, "No Form Data"
    
    n_matches = len(recent)
    weights = list(range(n_matches, 0, -1))  # [5, 4, 3, 2, 1] for N=5
    total_weight = sum(weights)
    
    weighted_points = 0
    max_weighted_points = total_weight * 3
    form_string = []
    
    for idx, m in enumerate(recent):
        is_home = m["home_team_id"] == team_id
        score_self = m["home_score"] if is_home else m["away_score"]
        score_opp = m["away_score"] if is_home else m["home_score"]
        
        weight = weights[idx]
        
        if score_self > score_opp:
            weighted_points += 3 * weight
            form_string.append("W")
        elif score_self == score_opp:
            weighted_points += 1 * weight
            form_string.append("D")
        else:
            form_string.append("L")
            
    form_ratio = weighted_points / max_weighted_points
    # Map form ratio to a wider modifier range: 0.65 (worst form) to 1.35 (best form)
    modifier = 0.65 + (form_ratio * 0.70)
    
    # Form text reads from oldest to newest (left to right)
    form_text = "-".join(reversed(form_string))
    
    return modifier, form_text

def get_h2h_blend(match_id):
    """
    Fetch and parse H2H data from API.
    Returns (h2h_wins_home, h2h_draws, h2h_wins_away, total_matches).
    """
    try:
        h2h_data = api_client.get_match_h2h(match_id)
        if not h2h_data or 'aggregates' not in h2h_data:
            return None
            
        aggr = h2h_data['aggregates']
        total = aggr.get('numberOfMatches', 0)
        if total == 0:
            return None
            
        home_wins = aggr['homeTeam'].get('wins', 0)
        away_wins = aggr['awayTeam'].get('wins', 0)
        draws = aggr.get('draws', 0)
        
        # In H2H endpoint, sometimes homeTeam/awayTeam maps directly to match order.
        # Let's double check alignment using team IDs
        match_info = h2h_data.get('match', {})
        db_home_id = match_info.get('homeTeam', {}).get('id')
        
        # If the order is reversed in the H2H object compared to the database match
        # (should not normally happen, but good to check)
        h2h_home_id = h2h_data.get('homeTeam', {}).get('id')
        if db_home_id and h2h_home_id and db_home_id != h2h_home_id:
            home_wins, away_wins = away_wins, home_wins
            
        return {
            "home_prob": home_wins / total,
            "draw_prob": draws / total,
            "away_prob": away_wins / total,
            "total_matches": total
        }
    except Exception as e:
        print(f"[WARNING] Error fetching H2H: {e}")
        return None

def calculate_match_prediction(match_id, competition_code, is_neutral=False):
    """
    Main entry point for predictions.
    Retrieves match details, runs Poisson simulation, applies Form & H2H adjustments,
    saves the prediction, and returns the result dictionary.
    """
    # 1. Fetch match details from database
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.*, 
               t_home.name AS home_name, 
               t_away.name AS away_name
        FROM matches m
        JOIN teams t_home ON m.home_team_id = t_home.id
        JOIN teams t_away ON m.away_team_id = t_away.id
        WHERE m.id = ?
        """,
        (match_id,)
    )
    match_row = cursor.fetchone()
    conn.close()
    
    if not match_row:
        raise ValueError(f"Match with ID {match_id} not found in database.")
        
    comp_id = match_row["competition_id"]
    home_id = match_row["home_team_id"]
    away_id = match_row["away_team_id"]
    home_name = match_row["home_name"]
    away_name = match_row["away_name"]
    stage = match_row["stage"]
    
    # Automatically treat World Cup knockout matches, finals, etc. as neutral
    if competition_code == "WC" or stage in ["ROUND_OF_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"]:
        is_neutral = True
        
    # 2. Get Team Stats
    home_stats = get_team_stats(home_id, comp_id)
    away_stats = get_team_stats(away_id, comp_id)
    avg_goals = get_league_average_goals(comp_id)
    
    # 3. Calculate Poisson expected goals
    # Calculate attack/defense strength with smoothing to prevent 0.0 values (e.g. from clean sheets)
    if home_stats["played"] > 0:
        home_att = ((home_stats["goals_for"] + 0.5) / (home_stats["played"] + 0.5)) / avg_goals
        home_def = ((home_stats["goals_against"] + 0.5) / (home_stats["played"] + 0.5)) / avg_goals
    else:
        home_att, home_def = 1.0, 1.0
        
    if away_stats["played"] > 0:
        away_att = ((away_stats["goals_for"] + 0.5) / (away_stats["played"] + 0.5)) / avg_goals
        away_def = ((away_stats["goals_against"] + 0.5) / (away_stats["played"] + 0.5)) / avg_goals
    else:
        away_att, away_def = 1.0, 1.0
        
    # Base Expected goals (xG)
    expected_home = home_att * away_def * avg_goals
    expected_away = away_att * home_def * avg_goals
    
    # Apply standard home advantage (10% boost to home, 10% penalty to away) if not neutral
    if not is_neutral:
        expected_home *= 1.10
        expected_away *= 0.90
        
    # 4. Form adjustment
    home_form_mod, home_form_str = get_team_form_modifier(home_id)
    away_form_mod, away_form_str = get_team_form_modifier(away_id)
    
    expected_home *= home_form_mod
    expected_away *= away_form_mod
    
    # Ensure expected goals are non-negative and capped realistically
    expected_home = max(0.1, min(expected_home, 5.0))
    expected_away = max(0.1, min(expected_away, 5.0))
    
    # 5. Poisson simulation (up to 8 goals each)
    p_home_win = 0.0
    p_draw = 0.0
    p_away_win = 0.0
    p_over_2_5 = 0.0
    p_under_2_5 = 0.0
    p_btts_yes = 0.0
    p_btts_no = 0.0
    score_probs = []
    
    for h in range(9):
        p_h = poisson_probability(expected_home, h)
        for a in range(9):
            p_a = poisson_probability(expected_away, a)
            joint_p = p_h * p_a
            
            if h > a:
                p_home_win += joint_p
            elif h == a:
                p_draw += joint_p
            else:
                p_away_win += joint_p
                
            # Over / Under 2.5
            if h + a > 2.5:
                p_over_2_5 += joint_p
            else:
                p_under_2_5 += joint_p
                
            # BTTS
            if h >= 1 and a >= 1:
                p_btts_yes += joint_p
            else:
                p_btts_no += joint_p
                
            # Score
            score_probs.append({
                "score": f"{h}-{a}",
                "prob": joint_p
            })
                
    # Normalize probabilities to sum to 1.0
    total_p = p_home_win + p_draw + p_away_win
    prob_home = p_home_win / total_p
    prob_draw = p_draw / total_p
    prob_away = p_away_win / total_p
    
    # Normalize O/U and BTTS
    total_ou = p_over_2_5 + p_under_2_5
    prob_over = p_over_2_5 / total_ou
    prob_under = p_under_2_5 / total_ou
    
    total_btts = p_btts_yes + p_btts_no
    prob_btts_yes = p_btts_yes / total_btts
    prob_btts_no = p_btts_no / total_btts
    
    # Sort score probabilities
    score_probs.sort(key=lambda x: x["prob"], reverse=True)
    top_scores = []
    for item in score_probs[:3]:
        score_str = item["score"]
        prob_val = item["prob"] / total_p
        odds_val = round(1.0 / prob_val, 2) if prob_val > 0 else 99.0
        top_scores.append({
            "score": score_str,
            "prob": round(prob_val * 100, 1),
            "odds": odds_val
        })
    
    # 6. H2H Blend (if data exists)
    # Give H2H stats a 25% weight in the final probability if there are at least 3 historical matches
    h2h = get_h2h_blend(match_id)
    h2h_used = False
    
    if h2h and h2h["total_matches"] >= 3:
        weight = 0.25
        prob_home = (1 - weight) * prob_home + weight * h2h["home_prob"]
        prob_draw = (1 - weight) * prob_draw + weight * h2h["draw_prob"]
        prob_away = (1 - weight) * prob_away + weight * h2h["away_prob"]
        h2h_used = True
        
    # Calculate Fair Odds (1 / probability)
    odds_home = round(1.0 / prob_home, 2) if prob_home > 0 else 99.0
    odds_draw = round(1.0 / prob_draw, 2) if prob_draw > 0 else 99.0
    odds_away = round(1.0 / prob_away, 2) if prob_away > 0 else 99.0
    
    # Save prediction to DB
    database.save_prediction(
        match_id=match_id,
        prob_home=prob_home,
        prob_draw=prob_draw,
        prob_away=prob_away,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away
    )
    
    # 7. Fetch Polymarket Odds
    poly_odds = api_client.get_polymarket_odds(home_name, away_name, competition_code)
    
    # Calculate O/U and BTTS odds
    odds_over = round(1.0 / prob_over, 2) if prob_over > 0 else 99.0
    odds_under = round(1.0 / prob_under, 2) if prob_under > 0 else 99.0
    odds_btts_yes = round(1.0 / prob_btts_yes, 2) if prob_btts_yes > 0 else 99.0
    odds_btts_no = round(1.0 / prob_btts_no, 2) if prob_btts_no > 0 else 99.0
    
    # Calculate To Advance / To Qualify (knockout stages)
    is_knockout = stage in ["ROUND_OF_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"]
    to_advance = None
    if is_knockout:
        # Overtime expected goals (30 mins is exactly 1/3 of 90 mins)
        expected_home_ot = expected_home / 3.0
        expected_away_ot = expected_away / 3.0
        
        # Simulate Overtime using Poisson
        p_home_ot = 0.0
        p_away_ot = 0.0
        p_draw_ot = 0.0
        
        for h in range(4):
            for a in range(4):
                prob_h = poisson_probability(expected_home_ot, h)
                prob_a = poisson_probability(expected_away_ot, a)
                joint_p = prob_h * prob_a
                
                if h > a:
                    p_home_ot += joint_p
                elif a > h:
                    p_away_ot += joint_p
                else:
                    p_draw_ot += joint_p
                    
        # Normalize Overtime probabilities
        total_ot = p_home_ot + p_away_ot + p_draw_ot
        if total_ot > 0:
            p_home_ot /= total_ot
            p_away_ot /= total_ot
            p_draw_ot /= total_ot
            
        # Combine normal time, overtime (30m), and penalty shootout (50-50)
        p_home_pen = 0.5
        p_away_pen = 0.5
        
        prob_advance_home = prob_home + prob_draw * (p_home_ot + p_draw_ot * p_home_pen)
        prob_advance_away = prob_away + prob_draw * (p_away_ot + p_draw_ot * p_away_pen)
        
        # Normalize final advance probabilities
        total_adv = prob_advance_home + prob_advance_away
        prob_advance_home /= total_adv
        prob_advance_away /= total_adv
        
        odds_adv_home = round(1.0 / prob_advance_home, 2) if prob_advance_home > 0 else 99.0
        odds_adv_away = round(1.0 / prob_advance_away, 2) if prob_advance_away > 0 else 99.0
        
        to_advance = {
            "prob_home": round(prob_advance_home * 100, 1),
            "prob_away": round(prob_advance_away * 100, 1),
            "odds_home": odds_adv_home,
            "odds_away": odds_adv_away
        }
    
    return {
        "match_id": match_id,
        "home_name": home_name,
        "away_name": away_name,
        "expected_home_goals": round(expected_home, 2),
        "expected_away_goals": round(expected_away, 2),
        "prob_home": round(prob_home * 100, 1),
        "prob_draw": round(prob_draw * 100, 1),
        "prob_away": round(prob_away * 100, 1),
        "odds_home": odds_home,
        "odds_draw": odds_draw,
        "odds_away": odds_away,
        "home_form": home_form_str,
        "away_form": away_form_str,
        "h2h_used": h2h_used,
        "h2h_matches": h2h["total_matches"] if h2h else 0,
        "is_neutral": is_neutral,
        "polymarket": poly_odds,
        "over_under": {
            "prob_over": round(prob_over * 100, 1),
            "prob_under": round(prob_under * 100, 1),
            "odds_over": odds_over,
            "odds_under": odds_under
        },
        "btts": {
            "prob_yes": round(prob_btts_yes * 100, 1),
            "prob_no": round(prob_btts_no * 100, 1),
            "odds_yes": odds_btts_yes,
            "odds_no": odds_btts_no
        },
        "top_scores": top_scores,
        "is_knockout": is_knockout,
        "to_advance": to_advance
    }
