import math
import database
import api_client

# ─── Knockout stage names across different competitions ───────────────────────
KNOCKOUT_STAGES = {
    # World Cup / Euros
    "ROUND_OF_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL",
    # UEFA Champions League / Europa League
    "LAST_16", "QUARTER_FINAL", "SEMI_FINAL",
    # Generic
    "KNOCKOUT", "PLAYOFF",
}

# ─── Neutral-ground competitions (no home advantage) ─────────────────────────
NEUTRAL_COMP_CODES = {"WC", "EC", "INT", "UCL_FINAL"}


def poisson_probability(lmbda, k):
    """Calculates P(X=k) for a Poisson distribution with mean lmbda."""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)


def get_team_stats(team_id, competition_id):
    """
    Aggregate team stats (played, goals_for, goals_against) from all FINISHED
    matches in this competition stored in the local database.
    Includes knockout matches that are absent from static standings tables.
    Falls back to standings table if no finished matches found yet.
    """
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            COUNT(*) as played,
            SUM(CASE WHEN home_team_id = ? THEN home_score ELSE away_score END) as goals_for,
            SUM(CASE WHEN home_team_id = ? THEN away_score ELSE home_score END) as goals_against
        FROM matches
        WHERE (home_team_id = ? OR away_team_id = ?)
          AND status = 'FINISHED'
          AND competition_id = ?
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

    # Fallback: standings table (group stage data)
    stats = database.get_team_stats_from_db(team_id, competition_id)
    if stats:
        return {
            "played": stats["played_games"],
            "goals_for": stats["goals_for"],
            "goals_against": stats["goals_against"]
        }

    return {"played": 0, "goals_for": 0, "goals_against": 0}


def get_league_average_goals(competition_id):
    """
    Calculates average goals scored per team per match in this competition.
    Falls back to the global football average (1.35) if no data.
    """
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
        return max(0.5, row["avg_goals"] / 2.0)  # per-team average, min 0.5

    return 1.35  # global football default


def get_team_form_modifier(team_id, limit=5):
    """
    Calculates a form modifier based on the team's last N matches
    across ALL competitions in the database (cross-competition form).

    Weights: most recent match = weight N, oldest = weight 1.
    Modifier range: 0.65 (terrible form) to 1.35 (hot streak).
    """
    recent = database.get_team_recent_matches(team_id, limit)
    if not recent:
        return 1.0, "No Data"

    n_matches = len(recent)
    weights = list(range(n_matches, 0, -1))   # e.g. [5, 4, 3, 2, 1]
    total_weight = sum(weights)
    max_weighted_points = total_weight * 3

    weighted_points = 0
    form_chars = []

    for idx, m in enumerate(recent):
        is_home = m["home_team_id"] == team_id
        score_self = m["home_score"] if is_home else m["away_score"]
        score_opp = m["away_score"] if is_home else m["home_score"]
        weight = weights[idx]

        if score_self > score_opp:
            weighted_points += 3 * weight
            form_chars.append("W")
        elif score_self == score_opp:
            weighted_points += 1 * weight
            form_chars.append("D")
        else:
            form_chars.append("L")

    form_ratio = weighted_points / max_weighted_points
    modifier = 0.65 + (form_ratio * 0.70)   # [0.65, 1.35]

    # Display from oldest → newest (left → right)
    form_text = "-".join(reversed(form_chars))
    return modifier, form_text


def get_h2h_blend(match_id):
    """
    Fetch H2H aggregates from the API.
    Returns blended probabilities or None if not enough history.
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

        # Verify team-order alignment
        match_info = h2h_data.get('match', {})
        db_home_id = match_info.get('homeTeam', {}).get('id')
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
        print(f"  [WARNING] H2H fetch error: {e}")
        return None


def _simulate_poisson_matrix(lambda_h, lambda_a, max_goals=8):
    """
    Run a Poisson score matrix up to max_goals.
    Returns (p_home_win, p_draw, p_away_win, p_over_2_5, p_btts_yes, score_list).
    """
    p_home_win = p_draw = p_away_win = 0.0
    p_over_2_5 = p_btts_yes = 0.0
    score_probs = []

    for h in range(max_goals + 1):
        p_h = poisson_probability(lambda_h, h)
        for a in range(max_goals + 1):
            p_a = poisson_probability(lambda_a, a)
            joint = p_h * p_a

            if h > a:
                p_home_win += joint
            elif h == a:
                p_draw += joint
            else:
                p_away_win += joint

            if h + a > 2:
                p_over_2_5 += joint
            if h >= 1 and a >= 1:
                p_btts_yes += joint

            score_probs.append({"score": f"{h}-{a}", "prob": joint})

    return p_home_win, p_draw, p_away_win, p_over_2_5, p_btts_yes, score_probs


def calculate_match_prediction(match_id, competition_code, is_neutral=False):
    """
    Main prediction engine.
    Steps: fetch match → compute xG → apply form → Poisson matrix →
           H2H blend → overtime/penalties (knockouts) → Polymarket comparison.
    """
    # ── 1. Fetch match from DB ─────────────────────────────────────────────
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.*,
               c.code as comp_code,
               t_home.name AS home_name,
               t_away.name AS away_name
        FROM matches m
        JOIN competitions c ON m.competition_id = c.id
        JOIN teams t_home ON m.home_team_id = t_home.id
        JOIN teams t_away ON m.away_team_id = t_away.id
        WHERE m.id = ?
        """,
        (match_id,)
    )
    match_row = cursor.fetchone()
    conn.close()

    if not match_row:
        raise ValueError(f"Match ID {match_id} not found in database.")

    comp_id = match_row["competition_id"]
    home_id = match_row["home_team_id"]
    away_id = match_row["away_team_id"]
    home_name = match_row["home_name"]
    away_name = match_row["away_name"]
    stage = match_row["stage"] or ""
    comp_code = match_row["comp_code"] or competition_code

    # ── 2. Neutral ground detection ────────────────────────────────────────
    # Always neutral: World Cup, Euros, known knockout stages, or explicit flag
    if (comp_code in NEUTRAL_COMP_CODES
            or stage.upper() in KNOCKOUT_STAGES
            or is_neutral):
        is_neutral = True

    # ── 3. Team stats & league average ────────────────────────────────────
    home_stats = get_team_stats(home_id, comp_id)
    away_stats = get_team_stats(away_id, comp_id)
    avg_goals = get_league_average_goals(comp_id)

    # ── 4. Attack / Defense strengths with Laplace smoothing (+0.5) ───────
    def strength(goals, played):
        return ((goals + 0.5) / (played + 0.5)) / avg_goals if played > 0 else 1.0

    home_att = strength(home_stats["goals_for"], home_stats["played"])
    home_def = strength(home_stats["goals_against"], home_stats["played"])
    away_att = strength(away_stats["goals_for"], away_stats["played"])
    away_def = strength(away_stats["goals_against"], away_stats["played"])

    # Base Expected Goals
    expected_home = home_att * away_def * avg_goals
    expected_away = away_att * home_def * avg_goals

    # ── 5. Home advantage (only for non-neutral venues) ───────────────────
    if not is_neutral:
        expected_home *= 1.10
        expected_away *= 0.90

    # ── 6. Cross-competition form modifier ────────────────────────────────
    home_form_mod, home_form_str = get_team_form_modifier(home_id)
    away_form_mod, away_form_str = get_team_form_modifier(away_id)

    expected_home = max(0.1, min(expected_home * home_form_mod, 5.0))
    expected_away = max(0.1, min(expected_away * away_form_mod, 5.0))

    # ── 7. Poisson score matrix ───────────────────────────────────────────
    p_home_win, p_draw, p_away_win, p_over_2_5, p_btts_yes, score_probs = \
        _simulate_poisson_matrix(expected_home, expected_away, max_goals=8)

    # Normalise
    total_1x2 = p_home_win + p_draw + p_away_win
    prob_home = p_home_win / total_1x2
    prob_draw = p_draw / total_1x2
    prob_away = p_away_win / total_1x2

    total_ou = p_over_2_5 + (1.0 - p_over_2_5)
    prob_over = p_over_2_5
    prob_under = 1.0 - p_over_2_5

    total_btts = p_btts_yes + (1.0 - p_btts_yes)
    prob_btts_yes = p_btts_yes
    prob_btts_no = 1.0 - p_btts_yes

    # Top-3 correct scores
    score_probs.sort(key=lambda x: x["prob"], reverse=True)
    top_scores = []
    for item in score_probs[:3]:
        prob_val = item["prob"] / total_1x2
        odds_val = round(1.0 / prob_val, 2) if prob_val > 0 else 99.0
        h_goals, a_goals = item["score"].split("-")
        top_scores.append({
            "score": f"{home_name} {h_goals} - {a_goals} {away_name}",
            "prob": round(prob_val * 100, 1),
            "odds": odds_val
        })

    # ── 8. H2H blend (25% weight, min 3 matches) ─────────────────────────
    h2h = get_h2h_blend(match_id)
    h2h_used = False
    if h2h and h2h["total_matches"] >= 3:
        w = 0.25
        prob_home = (1 - w) * prob_home + w * h2h["home_prob"]
        prob_draw = (1 - w) * prob_draw + w * h2h["draw_prob"]
        prob_away = (1 - w) * prob_away + w * h2h["away_prob"]
        h2h_used = True

    # Fair odds
    def fair_odds(p):
        return round(1.0 / p, 2) if p > 0 else 99.0

    odds_home = fair_odds(prob_home)
    odds_draw = fair_odds(prob_draw)
    odds_away = fair_odds(prob_away)

    # Save to DB
    database.save_prediction(match_id, prob_home, prob_draw, prob_away,
                             odds_home, odds_draw, odds_away)

    # ── 9. Polymarket live odds ───────────────────────────────────────────
    poly_odds = api_client.get_polymarket_odds(home_name, away_name, comp_code)

    # ── 10. Knockout: Overtime + Penalty simulation ───────────────────────
    is_knockout = stage.upper() in KNOCKOUT_STAGES
    to_advance = None

    if is_knockout:
        # OT xG = 1/3 of normal time (30 min vs 90 min)
        ot_h, ot_a = expected_home / 3.0, expected_away / 3.0
        p_h_ot, p_d_ot, p_a_ot, _, _, _ = _simulate_poisson_matrix(ot_h, ot_a, max_goals=3)

        total_ot = p_h_ot + p_d_ot + p_a_ot
        if total_ot > 0:
            p_h_ot /= total_ot
            p_a_ot /= total_ot
            p_d_ot /= total_ot

        # Penalties: 50-50
        p_adv_home = prob_home + prob_draw * (p_h_ot + p_d_ot * 0.5)
        p_adv_away = prob_away + prob_draw * (p_a_ot + p_d_ot * 0.5)
        total_adv = p_adv_home + p_adv_away
        p_adv_home /= total_adv
        p_adv_away /= total_adv

        to_advance = {
            "prob_home": round(p_adv_home * 100, 1),
            "prob_away": round(p_adv_away * 100, 1),
            "odds_home": fair_odds(p_adv_home),
            "odds_away": fair_odds(p_adv_away)
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
            "odds_over": fair_odds(prob_over),
            "odds_under": fair_odds(prob_under)
        },
        "btts": {
            "prob_yes": round(prob_btts_yes * 100, 1),
            "prob_no": round(prob_btts_no * 100, 1),
            "odds_yes": fair_odds(prob_btts_yes),
            "odds_no": fair_odds(prob_btts_no)
        },
        "top_scores": top_scores,
        "is_knockout": is_knockout,
        "to_advance": to_advance
    }
