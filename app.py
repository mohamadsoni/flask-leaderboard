import requests
import pandas as pd
import time
import os
from flask import Flask, render_template
from datetime import datetime

app = Flask(__name__)

# **Strava API Credentials** (Ganti dengan data API Strava kamu)
CLIENT_ID = "150348"
CLIENT_SECRET = "6281b45348ab44737877ebed01117c46ab0068f1"
REFRESH_TOKEN = "a99f8df8611688ddf512a6b44a7ec0a3570116ee"
ACCESS_TOKEN = None
EXPIRES_AT = 0

# **Function untuk Refresh Token Otomatis**
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

        url = "https://www.strava.com/api/v3/clubs/1415067/activities"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"after": 1740787200, "page": 1, "per_page": 200}

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return pd.DataFrame()

        activities = response.json()
        if not activities:
            return pd.DataFrame()

        df = pd.DataFrame(activities)

        # **Filter hanya aktivitas lari (Run)**
        if 'sport_type' in df.columns:
            df = df[df['sport_type'] == 'Run']

        # **Ambil data peserta (Firstname + Lastname)**
        if 'athlete' in df.columns:
            df['athlete_name'] = df['athlete'].apply(
                lambda x: f"{x['firstname']} {x['lastname'][0]}." if isinstance(x, dict) and 'firstname' in x and 'lastname' in x else 'Unknown'
            )
        
        # **Pilih Kolom yang Dibutuhkan**
        df = df[['athlete_name', 'distance', 'moving_time', 'total_elevation_gain']]

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
        leaderboard = leaderboard.sort_values(by="distance", ascending=False).reset_index(drop=True)

        # **Hitung Average Pace (menit/km)**
        leaderboard['avg_pace'] = (leaderboard['moving_time'] * 60) / leaderboard['distance']
        leaderboard['avg_pace'] = leaderboard['avg_pace'].apply(lambda x: f"{int(x)}:{int((x - int(x)) * 60):02d} min/km" if x > 0 else "--")

        # **Tambahkan Waktu Update Data**
        last_update = datetime.now().strftime("%d %B %Y, %H:%M:%S")

        return leaderboard.to_dict(orient='records'), last_update

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return pd.DataFrame(), None

# **Route Utama**
@app.route('/')
def index():
    leaderboard, last_update = get_leaderboard()
    if not leaderboard:
        return "<h2>No data available for the selected period.</h2>"

    return render_template('index.html', tables=leaderboard, last_update=last_update)

# **Menjalankan Flask App**
if __name__ == '__main__':
    app.run(debug=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Pastikan pakai port 8080
    app.run(host="0.0.0.0", port=port)  # Harus binding ke 0.0.0.0
