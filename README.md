# WeBallinGang - Advanced Sportsbook Analyst & Poisson Calculator ⚽📈

**WeBallinGang** is a local, advanced football analytics tool and sportsbook calculator. It mathematically models match probabilities using a **Poisson Distribution (Expected Goals - xG)**, scales results using a **Weighted Recency Form** modifier (capturing hot streaks and momentum **across all competitions**), blends historical Head-to-Head (H2H) records, and simulates **Overtime** and **Penalty Shootouts** for knockout stage matches.

The program integrates in real-time with the **Polymarket Gamma API** to fetch market odds and automatically detect statistical discrepancies (**Value Bets**).

> **Now supports:** La Liga · UEFA Champions League · Premier League · Bundesliga · Serie A · Ligue 1 · FIFA World Cup · Euros · International Friendlies

---

## 🚀 Key Features

1. **Precision Poisson xG Engine:**
   * Computes team-specific Attack and Defense strengths dynamically from the local database.
   * Employs *Laplace Additive Smoothing* (+0.5 goals/games) to prevent statistical anomalies (e.g., a team with clean sheets yielding 0 xG for opponents).
   * Generates fair probabilities for Moneyline (1X2), Over/Under 2.5 Goals, and Both Teams to Score (BTTS) markets.

2. **Cross-Competition Weighted Form (Momentum Tracker):**
   * Analyzes a team's last 5 matches **across all competitions** in the database (e.g., Real Madrid's form covers both La Liga AND UCL games).
   * Applies linear recency weights — the most recent match is weighted 5x more than the oldest.
   * Adjusts Expected Goals using a form multiplier ranging from `0.65` (terrible form) to `1.35` (hot streak).

3. **Knockout Stage Simulation (Overtime & Penalties):**
   * For knockout matches, the engine simulates a 30-minute Overtime period using $1/3$ of the 90-minute xG.
   * Models penalty shootouts as a 50-50 coin-toss to generate precise probabilities for the **To Advance / To Qualify** market.
   * Automatically detects knockout stage format for both **World Cup** (`ROUND_OF_16`, `QUARTER_FINALS`) and **UCL** (`LAST_16`, `QUARTER_FINAL`).

4. **🔥 Best Bet Scanner:**
   * Scans all scheduled matches (or a specific league / match) and ranks every betting market by potential value.
   * **Section 1 — Value Bets:** Compares fair odds against live Polymarket odds. Highlights markets where `poly_odds > fair_odds` and calculates the edge percentage.
   * **Section 2 — High-Confidence Bets:** Lists all markets with >= 65% model probability, with a visual confidence bar.
   * Can be scoped to: all leagues, a single competition, or a single match ID.

5. **Automatic Rate-Limit Retry:**
   * If the Football Data API returns a `429 Too Many Requests`, the bot automatically waits 61 seconds and retries — no crash, no manual intervention needed.

6. **Multi-Competition Sync:**
   * **Single sync:** Sync any supported competition by code.
   * **Quick sync all:** Sync La Liga, UCL, PL, Bundesliga, Serie A, and Ligue 1 in one go.
   * **Date-range sync:** Pull matches across a date window (useful for International Friendlies).

7. **Dual Interface Options:**
   * **Terminal CLI (`main.py`):** Fast, lightweight, 100% local, and free of API rate limits.
   * **Local Web App (`server.py`):** A Glassmorphism dark-mode UI with an interactive chatbot powered by Gemini AI (Function Calling).

---

## 🧮 Mathematical Model Deep-Dive

### 1. Expected Goals (xG) Estimation

**League/Tournament Average Goals per Team:**

$$\text{Avg}_{\text{Goals}} = \frac{\text{Total Goals Scored}}{2 \times \text{Total Finished Matches}}$$

**Attack and Defense Strength (with Laplace Smoothing):**

$$\text{Attack Strength (Home)} = \frac{\frac{\text{Goals Scored by Home} + 0.5}{\text{Matches Played} + 0.5}}{\text{Avg}_{\text{Goals}}}$$

$$\text{Defense Strength (Away)} = \frac{\frac{\text{Goals Conceded by Away} + 0.5}{\text{Matches Played} + 0.5}}{\text{Avg}_{\text{Goals}}}$$

**Base Expected Goals (xG):**

$$\text{Base xG}_{\text{Home}} = \text{Attack Strength}_{\text{Home}} \times \text{Defense Strength}_{\text{Away}} \times \text{Avg}_{\text{Goals}}$$

### 2. Weighted Form Modifier ($F$)
Last 5 matches across **all competitions**, weighted linearly $[5, 4, 3, 2, 1]$ (newest to oldest):

$$\text{Weighted Points} = \sum_{i=1}^{5} \text{Result Points}_i \times \text{Weight}_i$$

$$F = 0.65 + \left(\frac{\text{Weighted Points}}{45} \times 0.70\right), \quad F \in [0.65,\ 1.35]$$

$$\text{Adjusted xG} = \text{Base xG} \times F_{\text{Team}}$$

### 3. Poisson Score Matrix

$$P(k; \lambda) = \frac{\lambda^k e^{-\lambda}}{k!}$$

$$P(H, A) = P(H; \lambda_{\text{Home}}) \times P(A; \lambda_{\text{Away}})$$

An $8 \times 8$ matrix yields Home Win, Draw, Away Win, Over/Under 2.5, and BTTS probabilities.

### 4. Overtime & Penalty Shootout

$$\lambda_{\text{OT}} = \frac{\lambda_{\text{Normal}}}{3}$$

$$P(\text{Advance}_{\text{Home}}) = P(\text{Win}_{\text{90m}}) + P(\text{Draw}_{\text{90m}}) \times \left[P(\text{Win}_{\text{OT}}) + P(\text{Draw}_{\text{OT}}) \times 0.5\right]$$

---

## 🛠️ Installation & Setup

### 1. Prerequisites
Python 3.12 or 3.13.

### 2. Clone & Install Dependencies
```bash
cd "C:/Project Elite Ball Knowledge"
python -m pip install -r requirements.txt
```

### 3. Environment Variables
Create `.env` in the root directory:
```env
FOOTBALL_API_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_key_here
```

---

## 💻 Running the Application

### Mode A: Terminal CLI (Recommended)
```bash
python main.py
```

**Menu Options:**
| # | Option | Description |
|---|--------|-------------|
| 1 | Sync Single Competition | Sync standings + matches for one comp (e.g. `PD`, `CL`) |
| 2 | Quick Sync All | Sync La Liga, UCL, PL, BL1, SA, FL1 at once |
| 3 | Sync by Date Range | Pull matches across a date window (Friendlies, etc.) |
| 4 | List Matches + Predict | Browse DB matches, filter by comp, select to predict |
| 5 | Quick Predict by ID | Instant prediction by match ID |
| 6 | Run All Scheduled | Batch-predict all upcoming matches |
| **7** | **Best Bet Scanner** | **Find best bets right now across any scope** |
| 8 | Exit | — |

**CLI Shortcuts:**
```bash
python main.py sync PD         # Sync La Liga only
python main.py syncall         # Sync all active competitions
python main.py bestbets        # Launch Best Bet Scanner directly
```

### Mode B: Local Web App
```bash
python server.py
```
Open browser at 👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 📊 Best Bet Scanner Output Example

```
================================================================
              [1] VALUE BETS  (Polymarket odds > fair odds)
================================================================
  Match                             Market               Prob   Fair   Poly    Edge
  Real Madrid vs Barcelona          AWAY WIN            52.3%   1.91   2.20   +15.2%
  Man City vs Arsenal               HOME WIN            61.4%   1.63   1.95   +19.6%
----------------------------------------------------------------
              [2] HIGH-CONFIDENCE MODEL BETS  (>= 65% probability)
================================================================
  Match                             Market               Prob   Fair Odds   Confidence
  PSG vs Lyon                       HOME WIN            78.4%       1.28   [################----]
  Atletico vs Getafe                UNDER 2.5           71.2%       1.41   [##############------]
  Inter vs Monza                    BTTS NO             67.9%       1.47   [#############-------]
```

---

## ⚙️ Supported Competitions

| Code | Competition |
|------|-------------|
| `PD` | La Liga |
| `CL` | UEFA Champions League |
| `PL` | Premier League |
| `BL1` | Bundesliga |
| `SA` | Serie A |
| `FL1` | Ligue 1 |
| `WC` | FIFA World Cup |
| `EC` | European Championship |

---

## ⚙️ Directory Structure
```
C:/Project Elite Ball Knowledge/
│
├── api_client.py     # Football API + Polymarket integration, multi-comp sync
├── database.py       # SQLite schema + query utilities
├── calculator.py     # Poisson engine, cross-comp form, overtime simulation
├── main.py           # Terminal CLI + Best Bet Scanner
├── server.py         # Flask + Gemini AI chatbot
│
├── templates/
│   └── index.html    # Glassmorphism dark-mode UI
│
├── requirements.txt  # Python dependencies
├── .env              # API keys (git-ignored)
└── README.md
```

---

## 📝 License
Personal sports analytics project. Betting carries financial risk — use responsibly.
