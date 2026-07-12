# WeBallinGang - Advanced Sportsbook Analyst & Poisson Calculator ⚽📈

**WeBallinGang** is a local, advanced football analytics tool and sportsbook calculator. It mathematically models match probabilities using a **Poisson Distribution (Expected Goals - xG)**, scales results using a **Weighted Recency Form** modifier (capturing hot streaks and team momentum), blends historical Head-to-Head (H2H) records, and simulates **Overtime** and **Penalty Shootouts** for knockout stage matches.

The program integrates in real-time with the **Polymarket Gamma API** to fetch market odds and automatically detect statistical discrepancies (**Value Bets**).

---

## 🚀 Key Features

1. **Precision Poisson xG Engine:**
   * Computes team-specific Attack and Defense strengths dynamically from the database.
   * Employs *Laplace Additive Smoothing* (+0.5 goals/games) to prevent statistical anomalies (e.g., a team with clean sheets in group stages yielding 0 xG for opponents).
   * Generates fair probabilities for Moneyline (1X2), Over/Under 2.5 Goals, and Both Teams to Score (BTTS) markets.

2. **Weighted Recency Form (Momentum Tracker):**
   * Applies linear recency weights (the most recent match is weighted 5x more than the oldest) to accurately reflect current form and momentum.
   * Adjusts Expected Goals using a form multiplier ranging from `0.65` (poor form) to `1.35` (excellent form/hot streak).

3. **Knockout Stage Simulation (Overtime & Penalties):**
   * For knockout matches, the engine simulates a 30-minute Overtime period using $1/3$ of the 90-minute xG.
   * Models penalty shootouts as a 50-50 statistical coin-toss to generate precise probabilities for the **To Advance / To Qualify** market.

4. **Value Bet Detection:**
   * Compares the calculated fair odds against live Polymarket decimal odds.
   * Highlights profitable opportunities when market odds are higher than the model's calculated fair odds.
   * Automatically filters out resolved or dead markets (odds $\ge 50.0$).

5. **Dual Interface Options:**
   * **Terminal CLI (`main.py`):** Fast, lightweight, 100% offline-ready, and free of API rate limits.
   * **Local Web App (`server.py`):** A modern Glassmorphism dark-mode UI containing a match list dashboard and an interactive chatbot **WeBallinGang AI** powered by Gemini 3.5 Flash (Function Calling).

---

## 🧮 Mathematical Model Deep-Dive

The engine calculates football match probabilities using a multi-layered statistical approach. Below is the mathematical breakdown of how predictions are generated:

### 1. Expected Goals (xG) Estimation
The model first establishes the base scoring rate of the competition and the relative strengths of the competing teams.

*   **League/Tournament Average Goals per Team ($\text{Avg}_{\text{Goals}}$):**
    $$\text{Avg}_{\text{Goals}} = \frac{\text{Total Goals Scored in Tournament}}{2 \times \text{Total Finished Matches}}$$

*   **Attack and Defense Strength (with Laplace Smoothing):**
    To avoid extreme calculations (such as dividing by zero or getting $0.0$ xG for opponents playing a team with $100\%$ clean sheets), we apply additive smoothing ($+0.5$):
    $$\text{Attack Strength (Home)} = \frac{(\text{Goals Scored by Home} + 0.5) / (\text{Matches Played} + 0.5)}{\text{Avg}_{\text{Goals}}}$$
    $$\text{Defense Strength (Away)} = \frac{(\text{Goals Conceded by Away} + 0.5) / (\text{Matches Played} + 0.5)}{\text{Avg}_{\text{Goals}}}$$

*   **Base expected goals (xG) calculation:**
    $$\text{Base xG}_{\text{Home}} = \text{Attack Strength}_{\text{Home}} \times \text{Defense Strength}_{\text{Away}} \times \text{Avg}_{\text{Goals}}$$
    $$\text{Base xG}_{\text{Away}} = \text{Attack Strength}_{\text{Away}} \times \text{Defense Strength}_{\text{Home}} \times \text{Avg}_{\text{Goals}}$$

### 2. Weighted Form Modifier ($\mathbf{F}$)
We adjust base xG to reflect recent momentum. The last 5 matches are weighted linearly ($[5, 4, 3, 2, 1]$ from newest to oldest):
$$\text{Weighted Points} = \sum_{i=1}^{5} \text{Result Points}_i \times \text{Weight}_i$$
$$\text{Form Ratio} = \frac{\text{Weighted Points}}{\sum \text{Weights} \times 3} = \frac{\text{Weighted Points}}{45}$$
$$\text{Form Modifier } (F) = 0.65 + (\text{Form Ratio} \times 0.70)$$
$$\text{Adjusted xG} = \text{Base xG} \times F_{\text{Team}}$$

### 3. Poisson Probability Score Matrix
We model goal-scoring as a Poisson process. The probability of a team scoring exactly $k$ goals given an expected rate $\lambda$ (Adjusted xG) is:
$$P(k; \lambda) = \frac{\lambda^k e^{-\lambda}}{k!}$$

Assuming independence between team score lines, the probability of a specific scoreline $[H - A]$ (e.g., $2-1$) is the product of their individual Poisson probabilities:
$$P(H, A) = P(H; \lambda_{\text{Home}}) \times P(A; \lambda_{\text{Away}})$$

We construct a $6 \times 6$ grid (up to 5 goals each) to derive:
*   **Home Win Probability:** $\sum_{H > A} P(H, A)$
*   **Draw Probability:** $\sum_{H = A} P(H, A)$
*   **Away Win Probability:** $\sum_{H < A} P(H, A)$
*   **Over 2.5 Goals:** $\sum_{H + A \ge 3} P(H, A)$
*   **BTTS - Yes:** $\sum_{H \ge 1 \text{ and } A \ge 1} P(H, A)$

### 4. Overtime & Penalty Shootout Simulation
For knockout stages, if a match ends in a draw ($P(\text{Draw})$), it proceeds to Overtime (30 minutes) and potentially a Penalty Shootout.

*   **Overtime (OT) xG Simulation:**
    Since Overtime is 30 minutes long ($1/3$ of normal time), we scale the Adjusted xG:
    $$\lambda_{\text{OT}} = \frac{\lambda_{\text{Normal}}}{3}$$
    We then run a secondary Poisson matrix for the 30-minute OT period to calculate $P(\text{Win}_{\text{Home in OT}})$, $P(\text{Win}_{\text{Away in OT}})$, and $P(\text{Draw}_{\text{in OT}})$.

*   **Penalty Shootout:**
    Adu penalti dihitung sebagai peluang berimbang ($50\%$ chance for each team).

*   **Total Probability to Advance ($P(\text{Advance})$):**
    $$P(\text{Advance}_{\text{Home}}) = P(\text{Win}_{\text{Home in 90m}}) + P(\text{Draw}_{\text{in 90m}}) \times \left[ P(\text{Win}_{\text{Home in OT}}) + P(\text{Draw}_{\text{in OT}}) \times 0.5 \right]$$
    $$P(\text{Advance}_{\text{Away}}) = P(\text{Win}_{\text{Away in 90m}}) + P(\text{Draw}_{\text{in 90m}}) \times \left[ P(\text{Win}_{\text{Away in OT}}) + P(\text{Draw}_{\text{in OT}}) \times 0.5 \right]$$

---

## 🛠️ Installation & Setup

### 1. Prerequisites
Ensure you have Python (version 3.12 or 3.13) installed on your system.

### 2. Clone & Install Dependencies
Open your terminal inside the project directory and run:
```bash
# Navigate to the project directory
cd "C:/Project Elite Ball Knowledge"

# Install all required Python packages
python -m pip install -r requirements.txt
```

### 3. Environment Variables
Create a file named `.env` in the root directory and configure your API tokens:
```env
FOOTBALL_API_TOKEN=9dbfd450b0a34746ba25568665f6a0ae
GEMINI_API_KEY=AQ.Ab8RN6JU9JZfmiFU-nI9UftH24gfXnwwHZvLA2kKtC90rMlj2w
```

---

## 💻 Running the Application

### Mode A: Interactive Terminal CLI (Recommended)
Launch the CLI interface by running:
```bash
python main.py
```
**Options:**
1. **Sync Standings:** Updates the database with the latest league standings.
2. **Sync Matches:** Synchronizes latest match fixtures and completed scores.
3. **List Matches & Predict:** Shows scheduled fixtures. Enter the **Match ID** (e.g., `537387` for France vs. Spain) to run the simulation instantly!

---

### Mode B: Local Web App (AI Chatbot)
Start the local web server:
```bash
python server.py
```
Once active, open your browser and navigate to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

*Simply click any match card on the sidebar to prompt the AI to run a full analysis automatically!*

---

## 📊 Example Output (France vs. Spain - Semi-Final)

```text
============================================================
             PREDICTION RESULT: France vs Spain             
============================================================
Venue Context  : Neutral Ground
Form Home Team : France (W-W-W-W-W)
Form Away Team : Spain (W-W-W-W-W)
Expected Goals : France (0.5) | Spain (0.58)
------------------------------------------------------------
>>> MARKET: MONEYLINE (1X2)
  Model Prob   : [HOME: 18.8%]  [DRAW: 33.4%]  [AWAY: 22.8%]
  Model Odds   : [HOME: 5.32]  [DRAW: 2.99]  [AWAY: 4.39]
  Polymarket odds not found for this match.
------------------------------------------------------------
>>> MARKET: TO ADVANCE / TO QUALIFY (LOLOS KE BABAK BERIKUTNYA)
  France: Prob: 46.8% | Odds Wajar: 2.14
  Spain: Prob: 53.2% | Odds Wajar: 1.88
------------------------------------------------------------
>>> MARKET: OVER / UNDER 2.5 GOALS
  OVER 2.5 Goals : Prob: 9.6% | Odds Wajar: 10.44
  UNDER 2.5 Goals: Prob: 90.4% | Odds Wajar: 1.11
    -> Rekomendasi: UNDER 2.5 Goals (Peluang tinggi: 90.4%)
------------------------------------------------------------
>>> MARKET: BOTH TEAMS TO SCORE (BTTS)
  BTTS - YES (Kedua tim gol): Prob: 17.3% | Odds Wajar: 5.77
  BTTS - NO  (Salah satu/tidak gol): Prob: 82.7% | Odds Wajar: 1.21
    -> Rekomendasi: BTTS - NO (Peluang tinggi: 82.7%)
------------------------------------------------------------
>>> MARKET: TOP 3 CORRECT SCORE (TEBAK SKOR)
  1. Skor [France 0 - 0 Spain]: Prob: 33.9% | Odds Wajar: 2.95
  2. Skor [France 0 - 1 Spain]: Prob: 19.7% | Odds Wajar: 5.07
  3. Skor [France 1 - 0 Spain]: Prob: 17.0% | Odds Wajar: 5.89
------------------------------------------------------------
H2H Stats Used : Yes (based on 7 recent matches)
============================================================
```

---

## ⚙️ Directory Structure
```text
C:/Project Elite Ball Knowledge/
│
├── api_client.py          # Football API & Polymarket integration logic
├── database.py            # SQLite schema configuration & query utilities
├── calculator.py          # Mathematical engine (Poisson, form modifiers, overtime)
├── main.py                # Terminal-based interactive CLI
├── server.py              # Flask server and Gemini AI integration
│
├── templates/
│   └── index.html         # Glassmorphism dark-mode UI dashboard
│
├── requirements.txt       # Dependencies manifest
├── .env                   # Secret keys & API configurations (git-ignored)
└── README.md              # This file
```

---

## 📝 License
This project is for personal sports statistical analysis. Betting carries risk, and users are solely responsible for their financial decisions. Use responsibly!
