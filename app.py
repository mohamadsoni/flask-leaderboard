import requests
import pandas as pd
import time
import os
import logging
from flask import Flask, render_template
from datetime import datetime, timedelta

app = Flask(__name__)

# **Strava API Credentials** (Ganti dengan API Strava kamu)
CLIENT_ID = "150348"
CLIENT_SECRET = "6281b45348ab44737877ebed01117c46ab0068f1"
REFRESH_TOKEN = "a99f8df8611688ddf512a6b44a7ec0a3570116ee"
ACCESS_TOKEN = None
EXPIRES_AT = 0

# **Setup Logging**
logging.basicConfig(level=logging.DEBUG)

# **Tanggal Filter (1 Maret 2025)**
START_DATE = datetime(2025, 3, 1)
START_TIMESTAMP = int(START_DATE.timestamp())  # Konversi ke epoch time

# **Function untuk Refresh Token**
def refresh_access_token():
    global ACCESS_TOKEN, EXPIRES_AT, REFRESH_TOKEN

    if time.time() > EXPIRES_AT:
        print("\n===== Refreshing Strava Access Token =====")
        response = requests.post(
            "https://www.strava.com/api/v3/oauth/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": REFRESH_TOKEN
            }
        ).json()

        if "access_token" in response:
            ACCESS_TOKEN = response["access_token"]
            EXPIRES_AT = response["expires_at"]
            REFRESH_TOKEN = response["refresh_token"]
            print("✅ Token refreshed successfully!")
        else:
            print("❌ Failed to refresh token:", response)
            return None

    return ACCESS_TOKEN

# **Function untuk Ambil Data Leaderboard**
def get_leaderboard():
    try:
        token = refresh_access_token()
        if not token:
            return pd.DataFrame()

        all_activities = []
        page = 1
        max_pages = 10  # Batas maksimum pengambilan data agar tidak infinite loop
        last_data_length = 0  # Untuk cek apakah data berubah

        while page <= max_pages:
            url = f"https://www.strava.com/api/v3/clubs/1415067/activities"
            headers = {"Authorization": f"Bearer {token}"}
            params = {"after": START_TIMESTAMP, "page": page, "per_page": 200}

            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                break  # Hentikan jika gagal mengambil data

            activities = response.json()
            if not activities:
                print(f"✅ Page {page}: Tidak ada aktivitas baru, berhenti fetching.")
                break  # Hentikan jika API tidak mengembalikan aktivitas

            # **Cek apakah data sudah sama seperti sebelumnya (duplikasi)**
            if len(activities) == last_data_length:
                print(f"⚠️ Page {page}: Data tidak bertambah, berhenti fetching.")
                break

            all_activities.extend(activities)
            last_data_length = len(activities)  # Simpan jumlah terakhir
            print(f"📊 Page {page}: {len(activities)} aktivitas ditambahkan.")
            page += 1  # Lanjut ke halaman berikutnya

        if not all_activities:
            print("⚠️ Tidak ada aktivitas yang ditemukan setelah 1 Maret 2025.")
            return pd.DataFrame()

        df = pd.DataFrame(all_activities)

        # **Cek Kolom yang Tersedia**
        print(f"\n📊 Kolom yang tersedia di API: {list(df.columns)}")

        # **Filter hanya aktivitas Run, Walk, & Virtual Run**
        if 'sport_type' in df.columns:
            df = df[df['sport_type'].isin(['Run', 'Walk', 'VirtualRun'])]

        # **Ambil data peserta (Firstname + Lastname)**
        if 'athlete' in df.columns:
            df['athlete_name'] = df['athlete'].apply(
                lambda x: f"{x['firstname']} {x['lastname']}" if isinstance(x, dict) and 'firstname' in x and 'lastname' in x else 'Unknown'
            )

        # **Pilih Kolom yang Dibutuhkan**
        df = df[['athlete_name', 'distance', 'moving_time', 'total_elevation_gain', 'id'] if 'id' in df.columns else ['athlete_name', 'distance', 'moving_time', 'total_elevation_gain']]

        # **Hapus Data Duplikat**
        if 'id' in df.columns:
            df = df.drop_duplicates(subset=['id'], keep='first')
        else:
            df = df.drop_duplicates(subset=['athlete_name', 'distance', 'moving_time'], keep='first')

        print(f"\n✅ Total data setelah menghapus duplikasi: {len(df)}")

        # **Konversi distance ke km dan moving_time ke jam**
        df['distance'] = df['distance'] / 1000
        df['moving_time'] = df['moving_time'] / 3600

        # **Hitung Total Data Per Peserta**
        leaderboard = df.groupby('athlete_name').agg(
            total_activities=('distance', 'count'),
            distance=('distance', 'sum'),
            moving_time=('moving_time', 'sum'),
            total_elevation_gain=('total_elevation_gain', 'sum')
        ).reset_index()

        # **Sorting berdasarkan Distance (Descending)**
        leaderboard['total_activities'] = leaderboard['total_activities'].astype(int)
        leaderboard = leaderboard.sort_values(by="distance", ascending=False).reset_index(drop=True)

        # **Hitung Average Pace (menit/km)**
        leaderboard['avg_pace'] = (leaderboard['moving_time'] * 60) / leaderboard['distance']
        leaderboard['avg_pace'] = leaderboard['avg_pace'].apply(lambda x: f"{int(x)}:{int((x - int(x)) * 60):02d} min/km" if x > 0 else "--")

        # **Tambahkan Waktu Update Data**
        last_update = datetime.now().strftime("%d %B %Y, %H:%M:%S")

        print("\n🏃‍♂️ Leaderboard Final:")
        print(leaderboard)

        return leaderboard.to_dict(orient='records'), last_update

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return pd.DataFrame(), None

# **Route Utama**
@app.route('/')
def index():
    try:
        # Log setiap request yang masuk
        app.logger.info("Processing request for /")

        # Panggil fungsi leaderboard
        leaderboard, last_update = get_leaderboard()

        if not leaderboard:
            return "<h2>No data available for the selected period.</h2>"

        return render_template('index.html', tables=leaderboard, last_update=last_update)
    except Exception as e:
        app.logger.error(f"Internal Server Error: {e}")  # Log error di Railway
        return f"<h2>Internal Server Error: {str(e)}</h2>"

# **Menjalankan Flask App**
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))  # Pastikan pakai port 8080
    app.run(host="0.0.0.0", port=port, debug=True)  # Harus binding ke 0.0.0.0
