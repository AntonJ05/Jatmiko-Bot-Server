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
        # 1. DOWNLOAD DATA (Tetap 5 hari untuk stabilitas ADX)
        df = yf.download(symbol, period='5d', interval='1h', progress=False, auto_adjust=True)
        df.columns = df.columns.get_level_values(0) # Perbaikan Multi-Index
        if len(df) < 30: return None

        # 2. HITUNG INDIKATOR (ADX, BB, VOLUME)
        # Hitung TR, +DM, -DM untuk ADX
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

        # Bollinger Band untuk deteksi Pump
        ma20 = df['Close'].rolling(20).mean()
        std20 = df['Close'].rolling(20).std()
        df['upper_bb'] = ma20 + (2 * std20)

        # 3. AMBIL DATA TERAKHIR (C1=Sekarang, C2=Sebelumnya, C3=Dua jam lalu)
        c1 = df.iloc[-1]
        c2 = df.iloc[-2]
        c3 = df.iloc[-3]

        # --- DEFINISI VARIABEL (Untuk Menghilangkan Warning image_6af148.png) ---
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        is_whale = bool(c1['Volume'] > (avg_vol * 2))
        is_strong_trend = bool(c1['ADX'] > 25) # Menghilangkan warning baris 57
        status_tren = "STRONG" if is_strong_trend else "WEAK/SIDOWAYS"

        # 4. LOGIKA FVG (Fair Value Gap)
        fvg_detected = bool(c3['High'] < c2['Low']) # Gap antara candle 3 dan candle saat ini
        fvg_price = round(c3['High'], 4) if fvg_detected else 0
        
        # Menghilangkan warning status_fvg baris 59
        status_fvg = "DISCOUNT" if (fvg_detected and c1['Close'] <= fvg_price * 1.02) else "PREMIUM"
        if not fvg_detected: status_fvg = "NO GAP"

        # 5. KONFIRMASI CANDLESTICK (Price Action)
        is_bullish_engulfing = bool(c2['Close'] < c2['Open'] and c1['Close'] > c1['Open'] and c1['Close'] >= c2['Open'])
        is_hammer = bool((min(c1['Open'], c1['Close']) - c1['Low']) > (2 * abs(c1['Close'] - c1['Open'])))

        # 6. PENENTUAN SINYAL (ADX + FVG + CANDLE)
        sinyal = "WAIT"
        if is_strong_trend: # Penggunaan variabel yang aman
            if status_fvg == "DISCOUNT": # Penggunaan variabel yang aman
                if is_bullish_engulfing: sinyal = "🚀 STRONG BUY (ENGULFING)"
                elif is_hammer: sinyal = "🚀 STRONG BUY (HAMMER)"
                else: sinyal = "⏳ WAIT (CONFIRMATION)"
            else:
                sinyal = "⏳ WAIT (RETRACE)"
        # --- LOGIKA NOTIFIKASI TELEGRAM (Hanya untuk STRONG BUY) ---
        if "🚀 STRONG BUY" in sinyal:
            pesan_bot = (
                f"🔔 *SINYAL WHALE PUMP TERDETEKSI!*\n\n"
                f"🪙 *Koin:* {symbol.replace('-USD', '')}\n"
                f"💰 *Harga:* {round(c1['Close'], 4)}\n"
                f"📈 *Tren (ADX):* {round(c1['ADX'], 1)} (STRONG)\n"
                f"🎯 *Target Entry (FVG):* {fvg_price}\n"
                f"⚡ *Konfirmasi:* {sinyal.split('(')[1].replace(')', '')}\n"
                f"🛡️ *Zona:* DISCOUNT\n\n"
                f"🚀 _Segera cek Gate.io untuk eksekusi!_"
            )
            kirim_telegram(pesan_bot) # Memanggil fungsi dari image_6b55e5.png

        return {
            "KOIN": symbol.replace("-USD", ""),
            "HARGA": round(c1['Close'], 4),
            "ADX": round(c1['ADX'], 1),
            "TREN": status_tren,
            "FVG_AREA": fvg_price,
            "ZONE": status_fvg,
            "SINYAL": sinyal
        }
    except Exception as e:
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

