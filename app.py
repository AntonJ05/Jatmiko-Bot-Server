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
        df = yf.download(symbol, period='5d', interval='1h', progress=False, auto_adjust=True)
        if len(df) < 30: return None

        # --- ADOPSI ELITE CIRCLE TOOL: LOGIKA ADX (14) ---
        # Mengukur kekuatan tren [cite: 575, 576]
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
        df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        
        # ATR (14) untuk Volatilitas 
        df['ATR'] = df['TR'].rolling(14).mean()
        
        # Komponen ADX [cite: 575]
        df['+DM'] = (df['High'] - df['High'].shift(1)).clip(lower=0)
        df['-DM'] = (df['Low'].shift(1) - df['Low']).clip(lower=0)
        tr_smooth = df['TR'].rolling(14).mean()
        plus_di = 100 * (df['+DM'].rolling(14).mean() / tr_smooth)
        minus_di = 100 * (df['-DM'].rolling(14).mean() / tr_smooth)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.rolling(14).mean()

        # --- DATA TERAKHIR ---
        c = df.iloc[-1]
        p = df.iloc[-2]
        
        # Filter Kekuatan Tren [cite: 577]
        is_strong_trend = c['ADX'] > 25 
        status_tren = "STRONG" if is_strong_trend else "WEAK/SIDEWAYS"

        # --- LOGIKA WHALE + BOLLINGER BAND ---
        ma20 = df['Close'].rolling(20).mean()
        std20 = df['Close'].rolling(20).std()
        upper_bb = ma20 + (2 * std20)
        lower_bb = ma20 - (2 * std20)
        
        # Deteksi Whale (Volume > 2x Rata-rata)
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        is_whale = c['Volume'] > (avg_vol * 2)

        # --- PENENTUAN SINYAL ---
        sinyal = "WAIT"
        if is_whale and is_strong_trend:
            if c['Close'] > upper_bb.iloc[-1]:
                sinyal = "🚀 WHALE PUMP"
            elif c['Close'] < lower_bb.iloc[-1]:
                sinyal = "💀 WHALE DUMP"
        
        # --- ADOPSI GAINZALGO: SL BERDASARKAN ATR ---
        # SL diletakkan 1.5x jarak ATR dari harga sekarang [cite: 562, 563]
        dist = c['ATR'] * 1.5
        sl_atr = c['Close'] - dist if "PUMP" in sinyal else c['Close'] + dist

        return {
            "KOIN": symbol.replace("-USD", ""),
            "HARGA": round(c['Close'], 4),
            "ADX": round(c['ADX'], 1),
            "TREN": status_tren,
            "ATR_SL": round(sl_atr, 4),
            "SINYAL": sinyal
        }
    except: return None

# ================= 4. DASHBOARD UI =================
st.set_page_config(page_title="JatmikoHunter v2.5", layout="wide")
st.title("🛡️ JatmikoHunter v2.5")

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