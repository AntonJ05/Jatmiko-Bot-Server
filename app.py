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
    "ADA-USD", "RIVER-USD", "AVAX-USD", "FIL-USD", "IP-USD",
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
        # 1. AMBIL DATA (5 Hari agar ADX Akurat)
        df = yf.download(symbol, period='5d', interval='1h', progress=False, auto_adjust=True)
        df.columns = df.columns.get_level_values(0) # Perataan kolom
        if len(df) < 30: return None

        # 2. HITUNG ADX (Kekuatan Tren) [cite: 1225, 1226]
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
        df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        
        df['+DM'] = (df['High'] - df['High'].shift(1)).clip(lower=0)
        df['-DM'] = (df['Low'].shift(1) - df['Low']).clip(lower=0)
        tr_smooth = df['TR'].rolling(14).mean()
        plus_di = 100 * (df['+DM'].rolling(14).mean() / tr_smooth)
        minus_di = 100 * (df['-DM'].rolling(14).mean() / tr_smooth)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.rolling(14).mean()

        # 3. HITUNG BOLLINGER BAND & ATR [cite: 652]
        ma20 = df['Close'].rolling(20).mean()
        std20 = df['Close'].rolling(20).std()
        df['upper_bb'] = ma20 + (2 * std20)
        df['ATR'] = df['TR'].rolling(14).mean()

        # 4. DATA TERAKHIR & DETEKSI PAUS
        c1 = df.iloc[-1] # Candle saat ini
        c2 = df.iloc[-2] # Candle sebelumnya
        c3 = df.iloc[-3] # Candle ke-3 dari belakang
        
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        is_whale = bool(c1['Volume'] > (avg_vol * 2))
        is_strong_trend = bool(c1['ADX'] > 25)
        status_tren = "STRONG" if is_strong_trend else "WEAK/SIDOWAYS"

        # 5. LOGIKA FVG (Fair Value Gap) [cite: 1131, 1140]
        # Bullish FVG: High lilin 1 < Low lilin 3
        fvg_detected = bool(c3['High'] < c1['Low'])
        fvg_price = round(c3['High'], 4) if fvg_detected else 0
        
        # Area Discount: Jika harga sekarang dekat dengan gap [cite: 1108]
        status_fvg = "DISCOUNT" if (fvg_detected and c1['Close'] <= fvg_price * 1.02) else "PREMIUM"
        if not fvg_detected: status_fvg = "NO GAP"

        # 6. PENENTUAN SINYAL AKHIR
        sinyal = "WAIT"
        if is_whale and is_strong_trend:
            if c1['Close'] > c1['upper_bb']:
                if status_fvg == "DISCOUNT":
                    sinyal = "🚀 STRONG BUY (FVG)"
                else:
                    sinyal = "⏳ WAIT (RETRACE)" # Menunggu harga turun ke FVG [cite: 859]

        # SL Dinamis berdasarkan ATR [cite: 652]
        dist = c1['ATR'] * 1.5
        sl_fix = c1['Close'] - dist if "PUMP" in sinyal else c1['Close'] + dist

        return {
            "KOIN": symbol.replace("-USD", ""),
            "HARGA": round(c1['Close'], 4),
            "ADX": round(c1['ADX'], 1),
            "TREN": status_tren,
            "FVG_AREA": fvg_price,
            "ZONE": status_fvg,
            "ATR_SL": round(sl_fix, 4),
            "SINYAL": sinyal
        }
    except Exception as e:
        st.error(f"Error pada {symbol}: {e}")
        return None

# ================= 4. DASHBOARD UI =================
st.set_page_config(page_title="JatmikoHunter v2.5", layout="wide")
st.title("🛡️ JatmikoHunter v2.5")

dashboard_placeholder = st.empty()

while True:
    # 1. Buat variabel waktu khusus WITA (Balikpapan)
    tz_wita = pytz.timezone('Asia/Makassar') 
    waktu_lokal = datetime.now(tz_wita).strftime('%H:%M:%S')
    
    # 2. Tampilkan di dashboard agar sama dengan jam di HP Anda
    st.write(f"🔄 Memulai Pemindaian Baru (WITA): {waktu_lokal}")
    
    laporan = []
    
    for koin in DAFTAR_KOIN:
        hasil = hitung_sinyal(koin)
        if hasil:
            laporan.append(hasil)
            # Jeda agar tidak diblokir Yahoo Finance
            time.sleep(2) 
    
    # Tampilkan tabel hasil pemindaian
    st.table(pd.DataFrame(laporan))
    
    # Tunggu 1 menit sebelum scan ulang
    time.sleep(60)