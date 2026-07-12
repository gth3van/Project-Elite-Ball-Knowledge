import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soccer_bot.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Competitions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS competitions (
        id INTEGER PRIMARY KEY,
        code TEXT UNIQUE,
        name TEXT NOT NULL
    );
    """)
    
    # Teams Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        short_name TEXT,
        tla TEXT
    );
    """)
    
    # Matches Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY,
        competition_id INTEGER,
        home_team_id INTEGER,
        away_team_id INTEGER,
        utc_date TEXT NOT NULL,
        status TEXT NOT NULL,
        home_score INTEGER,
        away_score INTEGER,
        matchday INTEGER,
        stage TEXT,
        FOREIGN KEY (competition_id) REFERENCES competitions(id),
        FOREIGN KEY (home_team_id) REFERENCES teams(id),
        FOREIGN KEY (away_team_id) REFERENCES teams(id)
    );
    """)
    
    # Standings Table (for league context)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standings (
        competition_id INTEGER,
        team_id INTEGER,
        position INTEGER,
        played_games INTEGER,
        won INTEGER,
        draw INTEGER,
        lost INTEGER,
        points INTEGER,
        goals_for INTEGER,
        goals_against INTEGER,
        PRIMARY KEY (competition_id, team_id),
        FOREIGN KEY (competition_id) REFERENCES competitions(id),
        FOREIGN KEY (team_id) REFERENCES teams(id)
    );
    """)
    
    # Predictions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        match_id INTEGER PRIMARY KEY,
        prob_home REAL NOT NULL,
        prob_draw REAL NOT NULL,
        prob_away REAL NOT NULL,
        fair_odds_home REAL NOT NULL,
        fair_odds_draw REAL NOT NULL,
        fair_odds_away REAL NOT NULL,
        calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
    );
    """)
    
    conn.commit()
    conn.close()

def save_competition(id, code, name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO competitions (id, code, name) VALUES (?, ?, ?)",
        (id, code, name)
    )
    conn.commit()
    conn.close()

def save_team(id, name, short_name, tla):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO teams (id, name, short_name, tla) VALUES (?, ?, ?, ?)",
        (id, name, short_name, tla)
    )
    conn.commit()
    conn.close()

def save_match(id, competition_id, home_team_id, away_team_id, utc_date, status, home_score, away_score, matchday, stage):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO matches (id, competition_id, home_team_id, away_team_id, utc_date, status, home_score, away_score, matchday, stage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (id, competition_id, home_team_id, away_team_id, utc_date, status, home_score, away_score, matchday, stage)
    )
    conn.commit()
    conn.close()

def save_standing(competition_id, team_id, position, played_games, won, draw, lost, points, goals_for, goals_against):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO standings (competition_id, team_id, position, played_games, won, draw, lost, points, goals_for, goals_against)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (competition_id, team_id, position, played_games, won, draw, lost, points, goals_for, goals_against)
    )
    conn.commit()
    conn.close()

def save_prediction(match_id, prob_home, prob_draw, prob_away, odds_home, odds_draw, odds_away):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO predictions (match_id, prob_home, prob_draw, prob_away, fair_odds_home, fair_odds_draw, fair_odds_away)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (match_id, prob_home, prob_draw, prob_away, odds_home, odds_draw, odds_away)
    )
    conn.commit()
    conn.close()

def get_match_prediction(match_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM predictions WHERE match_id = ?", (match_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_team_stats_from_db(team_id, competition_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM standings WHERE team_id = ? AND competition_id = ?",
        (team_id, competition_id)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_team_recent_matches(team_id, limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    # Get last N matches that are FINISHED where the team played
    cursor.execute(
        """
        SELECT m.*, 
               t_home.name AS home_name, 
               t_away.name AS away_name
        FROM matches m
        JOIN teams t_home ON m.home_team_id = t_home.id
        JOIN teams t_away ON m.away_team_id = t_away.id
        WHERE (m.home_team_id = ? OR m.away_team_id = ?) AND m.status = 'FINISHED'
        ORDER BY m.utc_date DESC
        LIMIT ?
        """,
        (team_id, team_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
