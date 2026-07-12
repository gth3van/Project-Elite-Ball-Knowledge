# WeBallinGang - Advanced Sportsbook Analyst & Poisson Calculator ⚽📈

**WeBallinGang** adalah program analisis data sepak bola dan kalkulator taruhan sportsbook canggih yang berjalan secara lokal di komputer Anda. Program ini memodelkan probabilitas hasil pertandingan secara matematis menggunakan **Distribusi Poisson (Expected Goals - xG)**, tren momentum performa terkini (*Weighted Form*), data historis *Head-to-Head* (H2H), serta mensimulasikan babak **Overtime** dan **Adu Penalti** untuk pertandingan fase gugur.

Program ini juga terintegrasi secara dinamis dengan **Polymarket Gamma API** untuk menarik odds pasar secara real-time dan mendeteksi celah keuntungan taruhan secara statistik (**Value Bet**).

---

## 🚀 Fitur Utama

1. **Engine Prediksi Poisson (xG) Presisi:**
   * Menghitung kekuatan serang (*Attack Strength*) dan kekuatan bertahan (*Defense Strength*) setiap tim secara dinamis dari database pertandingan.
   * Dilengkapi *Laplace Additive Smoothing* (+0.5) untuk mencegah anomali matematika (seperti tim yang cleansheet 0 gol di fase grup).
   * Menghasilkan probabilitas murni untuk Moneyline (1X2), Over/Under 2.5 Goals, dan *Both Teams to Score* (BTTS).

2. **Model Momentum Tertimbang (*Weighted Recency Form*):**
   * Menganalisis tren performa 5 pertandingan terakhir.
   * Memberikan bobot dinamis linier (laga terbaru memiliki pengaruh 5x lipat lebih besar dibanding laga tertua) untuk menangkap tren performa/kemenangan beruntun secara akurat.
   * Pengaruh modifier performa berkisar dari `0.65` (sangat buruk) hingga `1.35` (sangat panas).

3. **Simulasi Knockout Terintegrasi (Overtime & Penalti):**
   * Khusus pertandingan babak gugur (*knockout*), bot mensimulasikan babak tambahan (Overtime 30 menit) menggunakan $1/3$ porsi kekuatan xG normal.
   * Mensimulasikan adu penalti secara statistik (50-50) untuk menghasilkan probabilitas pasar **To Advance / Lolos** secara akurat.

4. **Deteksi Celah Taruhan (*Value Bet Detector*):**
   * Membandingkan *fair odds* (odds wajar) kalkulasi matematis program dengan odds real-time di pasar Polymarket.
   * Memberikan rekomendasi taruhan otomatis jika odds di pasaran dinilai terlalu tinggi (menguntungkan).
   * Dilengkapi filter otomatis untuk mengabaikan bursa pasar taruhan yang sudah selesai/tutup (odds $\ge 50.0$).

5. **Dua Mode Tampilan Premium:**
   * **Mode CLI Terminal (`main.py`):** Cepat, hemat data, gratis selamanya, dan bebas kuota/limit API.
   * **Mode Web App Local (`server.py`):** Tampilan Glassmorphism dark mode modern dengan panel daftar jadwal tanding terintegrasi dan chatbot AI **WeBallinGang AI** berbasis Gemini 3.5 Flash (Function Calling).

---

## 🛠️ Persiapan & Instalasi

### 1. Prasyarat
Pastikan Anda sudah menginstal Python (versi 3.12 atau 3.13) di komputer Anda.

### 2. Kloning Repositori & Install Dependensi
Buka terminal Anda dan jalankan perintah berikut:
```bash
# Masuk ke folder proyek
cd "c:/Project Ball"

# Install seluruh library yang dibutuhkan
python -m pip install -r requirements.txt
```

### 3. Konfigurasi Lingkungan
Buat file bernama `.env` di direktori utama proyek Anda, lalu isi dengan format berikut:
```env
FOOTBALL_API_TOKEN=9dbfd450b0a34746ba25568665f6a0ae
GEMINI_API_KEY=AQ.Ab8RN6JU9JZfmiFU-nI9UftH24gfXnwwHZvLA2kKtC90rMlj2w
```

---

## 💻 Cara Menjalankan Program

### Mode A: Terminal CLI (Direkomendasikan & Bebas Kuota)
Untuk menjalankan versi terminal interaktif, jalankan perintah berikut:
```bash
python main.py
```
**Menu Pilihan:**
1. **Sync Standings:** Mengambil update klasemen liga terbaru.
2. **Sync Matches:** Mengambil update jadwal dan hasil skor pertandingan terbaru.
3. **List Matches & Predict:** Menampilkan daftar pertandingan aktif. Cukup ketikkan **ID Pertandingan** (misal: `537387` untuk Prancis vs Spanyol) untuk melihat analisis lengkapnya secara instan!

---

### Mode B: Local Web App (Chatbot AI Premium)
Jika Anda ingin berinteraksi dengan AI analis visual **WeBallinGang AI**, jalankan server lokal:
```bash
python server.py
```
Setelah server aktif, buka browser Anda dan akses alamat:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

*Anda bisa langsung mengklik kartu pertandingan di panel kiri browser untuk meminta AI menganalisis pertandingan tersebut secara otomatis!*

---

## 📊 Contoh Output Analisis (Prancis vs Spanyol - Semifinal)

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

## ⚙️ Struktur Folder Proyek
```text
c:/Project Ball/
│
├── api_client.py          # Logika pemanggilan Football-Data API & Polymarket API
├── database.py            # Skema database SQLite & fungsi kueri data lokal
├── calculator.py          # Engine matematika Poisson, form, dan simulasi overtime
├── main.py                # Antarmuka CLI interaktif untuk terminal
├── server.py              # Server web Flask terintegrasi Gemini AI 3.5 Flash
│
├── templates/
│   └── index.html         # Frontend Dashboard Chatbot Glassmorphism
│
├── requirements.txt       # Daftar pustaka dependensi Python
├── .env                   # Token & Kunci API sensitif (jangan di-commit ke Git)
└── README.md              # Panduan ini
```

---

## 📝 Lisensi
Proyek ini dibuat untuk tujuan analisis statistik olahraga pribadi. Segala bentuk keputusan taruhan yang diambil berdasarkan hasil kalkulasi bot ini sepenuhnya merupakan tanggung jawab pengguna. gunakan dengan bijak!
