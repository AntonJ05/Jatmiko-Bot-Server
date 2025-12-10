import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
from datetime import datetime
import pytz

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Jatmiko Hunter HYBRID", page_icon="🦅", layout="wide")

# --- INISIALISASI SESSION STATE (Untuk Anti-Spam & Auto Loop) ---
if 'last_scan_time' not in st.session_state:
    st.session_state['last_scan_time'] = None
if 'last_signals' not in st.session_state:
    st.session_state['last_signals'] = []
if 'is_running' not in st.session_state:
    st.session_state['is_running'] = False

# --- FUNGSI KIRIM TELEGRAM ---
def send_telegram(message):
    try:
        bot_token = st.secrets["telegram"]["token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal kirim Telegram: {e}")

# --- FUNGSI UTAMA (ENGINE) ---
def run_scanner(exchange_id, timeframe, limit_candle, symbols, modal_awal, resiko_per_trade, kirim_laporan):
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
        
        laporan_data = []
        strong_buy_list = []
        
        # Progress Bar hanya muncul jika manual, kalau auto pakai status text saja biar ringan
        status_placeholder = st.empty()
        
        for i, symbol in enumerate(symbols):
            status_placeholder.text(f"🦅 Memindai {symbol} ({i+1}/{len(symbols)})...")
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit_candle)
                df = pd.DataFrame(bars, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df['Time'] = pd.to_datetime(df['Time'], unit='ms')
                
                # Indikator
                df['EMA_50'] = ta.ema(df['Close'], length=50)
                df['EMA_200'] = ta.ema(df['Close'], length=200)
                df['RSI'] = ta.rsi(df['Close'], length=14)
                df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
                
                last = df.iloc[-1]
                avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
                
                # Logika
                is_uptrend = last['Close'] > last['EMA_200']
                rsi_valid = 40 < last['RSI'] < 70
                whale_detected = last['Volume'] > (1.5 * avg_vol)
                
                signal = "NEUTRAL"
                if is_uptrend and rsi_valid:
                    if whale_detected: signal = "STRONG BUY"
                    elif last['Close'] > last['EMA_50']: signal = "BUY DIP" # Sederhana
                
                # Hitung Risk
                atr = last['ATR']
                sl = last['Close'] - (2 * atr)
                tp = last['Close'] + (4 * atr)
                
                risk_amt = modal_awal * (resiko_per_trade / 100)
                dist_sl = (last['Close'] - sl) / last['Close']
                size = risk_amt / dist_sl if dist_sl > 0 else 0
                
                data_row = {
                    "Coin": symbol, "Price": last['Close'], "Signal": signal,
                    "RSI": round(last['RSI'], 2), "Whale": "YES" if whale_detected else "-",
                    "TP": round(tp, 4), "SL": round(sl, 4), "Size ($)": round(size, 2)
                }
                laporan_data.append(data_row)
                
                if signal == "STRONG BUY":
                    strong_buy_list.append(data_row)
                    
            except Exception:
                continue

        status_placeholder.empty() # Hapus status loading
        
        # --- LOGIKA TELEGRAM & ANTI-SPAM ---
        if kirim_laporan and strong_buy_list:
            # Cek apakah sinyal ini SAMA PERSIS dengan scan terakhir?
            current_signals_str = [x['Coin'] for x in strong_buy_list]
            
            if current_signals_str != st.session_state['last_signals']:
                # Ada sinyal baru/beda! Kirim!
                pesan = f"🦅 *SINYAL PAUS TERDETEKSI* 🦅\n⏰ {datetime.now().strftime('%H:%M')} WIB\n\n"
                for item in strong_buy_list:
                    pesan += f"🚀 *{item['Coin']}*\nHarga: {item['Price']}\nStopLoss: {item['SL']}\nTP: {item['TP']}\n\n"
                pesan += "_Cek Chart & DYOR!_"
                
                send_telegram(pesan)
                st.toast(f"Laporan {len(strong_buy_list)} koin dikirim!", icon="📨")
                
                # Update memori terakhir
                st.session_state['last_signals'] = current_signals_str
            else:
                st.toast("Sinyal masih sama, skip Telegram.", icon="zz")
        
        # Simpan waktu scan
        st.session_state['last_scan_time'] = datetime.now().strftime("%H:%M:%S")
        return pd.DataFrame(laporan_data)
        
    except Exception as e:
        st.error(f"Error Engine: {e}")
        return pd.DataFrame()

# --- TAMPILAN SIDEBAR ---
with st.sidebar:
    st.header("🦅 JATMIKO HYBRID")
    
    # Mode Operasi
    mode = st.radio("Mode Operasi", ["Manual (Klik)", "Otomatis (Loop)"])
    
    if mode == "Otomatis (Loop)":
        interval = st.select_slider("Scan Setiap:", options=[15, 30, 60], value=30, format_func=lambda x: f"{x} Menit")
        st.info(f"Bot akan scan otomatis setiap {interval} menit selama halaman ini terbuka.")
    
    st.divider()
    
    # Pilihan User
    exchange_id = st.selectbox("Exchange", ["gateio", "binance"])
    timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h"])
    # List Simbol (Versi Ringkas Golden 50)
    symbols = [
        # --- THE KINGS (Wajib Ada) ---
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
        
        # --- MEME COINS (Favorit Paus Gorengan) ---
        "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT", 
        "FLOKI/USDT", "MEME/USDT",
        
        # --- AI & DEPIN (Narasi Masa Depan) ---
        "RNDR/USDT", "FET/USDT", "GRT/USDT", "TAO/USDT", "NEAR/USDT",
        "FIL/USDT", "THETA/USDT",
        
        # --- LAYER 1 & 2 BARU (Sering Pump Kencang) ---
        "SUI/USDT", "SEI/USDT", "APT/USDT", "INJ/USDT", "TIA/USDT",
        "ARB/USDT", "OP/USDT", "IMX/USDT", "STX/USDT", "KAS/USDT",
        
        # --- DEFI & INFRASTRUCTURE (Fundamental Kuat) ---
        "LINK/USDT", "AVAX/USDT", "MATIC/USDT", "UNI/USDT", "LDO/USDT",
        "AAVE/USDT", "SNX/USDT", "RUNE/USDT", "FANTOM/USDT", "ADA/USDT",
        
        # --- LEGACY / OLD SCHOOL (Kadang Bangun Tiba-tiba) ---
        "LTC/USDT", "BCH/USDT", "TRX/USDT", "DOT/USDT", "ATOM/USDT",
        "XLM/USDT", "VET/USDT", "ETC/USDT", "EOS/USDT", "SAND/USDT"
    ]
    
    kirim_laporan = st.checkbox("Notifikasi Telegram", value=True)
    modal_awal = st.number_input("Modal ($)", 100.0)
    resiko = st.slider("Resiko %", 1, 5, 2)

# --- HALAMAN UTAMA ---
st.title("Radar Jatmiko: Hybrid Edition")

# Logika Tampilan Waktu
jkt_time = datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%H:%M WIB")
st.write(f"🕒 Waktu Server: **{jkt_time}** | Terakhir Scan: **{st.session_state['last_scan_time'] if st.session_state['last_scan_time'] else '-'}**")

# LOGIKA JALAN
df_result = pd.DataFrame()

if mode == "Manual (Klik)":
    if st.button("🚀 SCAN SEKARANG"):
        with st.spinner("Scanning Manual..."):
            df_result = run_scanner(exchange_id, timeframe, 100, symbols, modal_awal, resiko, kirim_laporan)

elif mode == "Otomatis (Loop)":
    # Tombol Start/Stop Loop
    col1, col2 = st.columns(2)
    if col1.button("▶️ MULAI AUTO PILOT"):
        st.session_state['is_running'] = True
    if col2.button("⏹️ STOP"):
        st.session_state['is_running'] = False
        
    if st.session_state['is_running']:
        st.success(f"✅ Auto Pilot AKTIF. Refresh tiap {interval} menit.")
        
        # Placeholder untuk hasil
        result_placeholder = st.empty()
        timer_placeholder = st.empty()
        
        # Loop Scanning
        while st.session_state['is_running']:
            # Jalankan Scan
            df_result = run_scanner(exchange_id, timeframe, 100, symbols, modal_awal, resiko, kirim_laporan)
            
            # Tampilkan Hasil di Placeholder
            if not df_result.empty:
                strong = df_result[df_result['Signal'] == "STRONG BUY"]
                with result_placeholder.container():
                    if not strong.empty:
                        st.dataframe(strong, use_container_width=True)
                    else:
                        st.info("Belum ada sinyal Strong Buy. Menunggu siklus berikutnya...")
            
            # Hitung Mundur (Countdown) agar user tahu bot masih hidup
            for s in range(interval * 60, 0, -1):
                mins, secs = divmod(s, 60)
                timer_placeholder.metric("Scan Berikutnya dalam:", f"{mins:02d}:{secs:02d}")
                time.sleep(1)
                
            # Rerun loop (akan kembali ke atas while)

# TAMPILAN HASIL (Hanya untuk Manual, karena Auto punya container sendiri)
if mode == "Manual (Klik)" and not df_result.empty:
    strong = df_result[df_result['Signal'] == "STRONG BUY"]
    others = df_result[df_result['Signal'] != "STRONG BUY"]
    
    st.subheader("🔥 HASIL SCAN")
    if not strong.empty:
        st.success(f"Ditemukan {len(strong)} Sinyal!")
        st.dataframe(strong)
    else:
        st.warning("Zonkm. Tidak ada Strong Buy.")
    
    with st.expander("Lihat Koin Lainnya"):
        st.dataframe(others)
