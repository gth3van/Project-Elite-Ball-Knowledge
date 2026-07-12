import os
import json
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import google.generativeai as genai
import database
import calculator

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='templates')

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# Define tools for Gemini
def list_available_matches() -> str:
    """
    Mengambil daftar pertandingan sepak bola yang ada di database lokal beserta ID, tim rumah, tim lawan, tanggal, dan statusnya.
    """
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, c.code as competition, t_home.name as home, t_away.name as away, 
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
        return json.dumps([dict(r) for r in rows])
    except Exception as e:
        return f"Error listing matches: {e}"

def predict_match(match_id: int) -> str:
    """
    Menghitung prediksi probabilitas (win/draw/loss), odds wajar, Over/Under 2.5 goals, BTTS, tebak skor (Correct Score), 
    serta membandingkannya dengan odds pasar real-time dari Polymarket.
    """
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT c.code FROM matches m JOIN competitions c ON m.competition_id = c.id WHERE m.id = ?",
            (match_id,)
        )
        row = cursor.fetchone()
        conn.close()
        comp_code = row['code'] if row else 'WC'
        
        res = calculator.calculate_match_prediction(match_id, comp_code)
        return json.dumps(res)
    except Exception as e:
        return f"Error predicting match ID {match_id}: {e}"

# Tools registration list
tools_list = [list_available_matches, predict_match]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/matches')
def get_matches():
    try:
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
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400
        
    try:
        # Initialize Gemini Model with tools
        model = genai.GenerativeModel(
            model_name='gemini-3.5-flash',
            tools=tools_list,
            system_instruction=(
                "Anda adalah seorang AI Analis Sepak Bola & Sportsbook profesional bernama 'WeBallinGang'. "
                "Tugas Anda adalah membantu pengguna menganalisis pertandingan sepak bola dan mendeteksi peluang taruhan 'Value Bet'. "
                "Gunakan data statistik rill dari database dan Polymarket melalui tools yang disediakan. "
                "Jika pengguna menanyakan prediksi suatu pertandingan, gunakan tool 'list_available_matches' untuk mencari ID pertandingan "
                "lalu gunakan tool 'predict_match' dengan ID tersebut. "
                "Jawablah dengan bahasa Indonesia yang santai, bersahabat, profesional, dan mudah dipahami. "
                "Jangan menyebutkan istilah 'HOME' atau 'AWAY' untuk taruhan, sebutkan nama timnya langsung agar pengguna paham. "
                "Format respons Anda dengan markdown yang rapi, berikan penekanan pada odds dan persentase probabilitas."
            )
        )
        
        # Start chat session with automatic function calling enabled
        chat_session = model.start_chat(enable_automatic_function_calling=True)
        response = chat_session.send_message(user_message)
        
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    database.init_db()
    app.run(host='127.0.0.1', port=5000)
