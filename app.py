import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
import pytz

# ================= 1. KONFIGURASI =================
TELEGRAM_TOKEN = "7965390627:AAHgyD0MCeB8sydAik8RiEuDvxIwETxcC4s"
TELEGRAM_CHAT_ID = "6244409531"

# Daftar 20 Koin Pilihan Anda (Format Yahoo Finance)
DAFTAR_KOIN = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "FIL-USD", "IP-USD",
    "DOT-USD", "LINK-USD", "DASH-USD", "LTC-USD", "TRX-USD",
    "BCH-USD", "NEAR-USD", "OP-USD", "XMR-USD", "FHE-USD"
]

# ================= 2. FUNGSI PENDUKUNG =================
def kirim_telegram(pesan):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "Markdown"}
        requests.get(url, params=params, timeout=5)
    except:
        pass

# ================= 3. LOGIKA SINYAL (VERSI STABIL) =================
def hitung_sinyal(symbol):
    try:
        # Ambil data dari Yahoo Finance (Lancar tanpa VPN)
        df = yf.download(symbol, period="5d", interval="1h", progress=False, auto_adjust=True)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # Indikator Dasar
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['STD_20'] = df['Close'].rolling(window=20).std()
        df['Upper_BB'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['Lower_BB'] = df['SMA_20'] - (df['STD_20'] * 2)
        df['Avg_Volume'] = df['Volume'].rolling(window=20).mean()
        
        curr = df.iloc[-1]
        is_whale = curr['Volume'] > (curr['Avg_Volume'] * 2.0)
        
        status = "WAIT"
        if curr['Close'] > curr['Upper_BB'] and is_whale:
            status = " 🐳 WHALE PUMP"
        elif curr['Close'] < curr['Lower_BB'] and is_whale:
            status = " 🐳 WHALE DUMP"
        
        return {
            "KOIN": symbol.replace("-USD", ""),
            "HARGA": f"{curr['Close']:,.4f}",
            "SINYAL": status,
            "VOL_WHALE": "YA" if is_whale else "TIDAK"
        }
    except:
        return None

# ================= 4. DASHBOARD UI =================
st.set_page_config(page_title="JatmikoHunter v2.3", layout="wide")
st.title("🛡️ JatmikoHunter v2.3")

dashboard_placeholder = st.empty()

while True:
    laporan = []
    wita = pytz.timezone('Asia/Makassar')
    jam_skrg = datetime.now(wita).strftime('%H:%M:%S')

    for koin in DAFTAR_KOIN:
        hasil = hitung_sinyal(koin)
        if hasil:
            laporan.append(hasil)
            # Kirim notif jika ada pergerakan Paus
            if "WHALE" in hasil['SINYAL']:
                kirim_telegram(f"🚨 {hasil['SINYAL']} ({hasil['KOIN']}) detect pada harga {hasil['HARGA']}")

    if laporan:
        with dashboard_placeholder.container():
            st.write(f"**Update Terakhir:** {jam_skrg} WITA")
            st.table(pd.DataFrame(laporan))
    
    time.sleep(60) # Refresh tiap 1 menit