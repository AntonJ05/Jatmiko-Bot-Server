import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Jatmiko Hunter Pro", page_icon="🦅", layout="wide")

# --- INISIALISASI SESSION STATE ---
if 'last_scan_time' not in st.session_state:
    st.session_state['last_scan_time'] = None
if 'last_signals' not in st.session_state:
    st.session_state['last_signals'] = []
if 'is_running' not in st.session_state:
    st.session_state['is_running'] = False

# --- CACHING EXCHANGE ---
@st.cache_resource
def get_exchange(exchange_id):
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
        return exchange
    except Exception:
        return None

# --- FUNGSI KIRIM TELEGRAM ---
def send_telegram(message):
    if "telegram" in st.secrets:
        try:
            bot_token = st.secrets["telegram"]["token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
            requests.post(url, json=payload)
        except Exception:
            pass

# --- FUNGSI UTAMA (ENGINE) ---
def run_scanner(exchange_id, timeframe, limit_candle, symbols, modal_awal, resiko_per_trade, kirim_laporan):
    exchange = get_exchange(exchange_id)
    if not exchange:
        st.error(f"Gagal memuat exchange {exchange_id}")
        return pd.DataFrame()

    laporan_data = []
    strong_buy_list = []
    
    # Placeholder Progress (Hanya muncul jika scan lebih dari 1 koin)
    progress_bar = None
    status_text = None
    if len(symbols) > 1:
        status_text = st.empty()
        progress_bar = st.progress(0)
    
    total_symbols = len(symbols)
    
    for i, symbol in enumerate(symbols):
        # Update progress bar jika banyak koin
        if len(symbols) > 1 and progress_bar:
            try:
                progress_percent = (i + 1) / total_symbols
                progress_bar.progress(progress_percent)
                status_text.text(f"🦅 Memindai {symbol} ({i+1}/{total_symbols})...")
            except:
                pass
        
        try:
            # Ambil data Candle
            # PENTING: Limit harus cukup untuk hitung EMA 200
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit_candle)
            
            if not bars:
                continue
                
            df = pd.DataFrame(bars, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['Time'] = pd.to_datetime(df['Time'], unit='ms')

            # PROTEKSI: Jika data kurang dari 200 candle, skip (karena EMA 200 butuh 200 data)
            if len(df) < 200:
                if len(symbols) == 1:
                    st.warning(f"Data {symbol} tidak cukup ({len(df)} candle). Butuh minimal 200.")
                continue
            
            # Indikator
            df['EMA_50'] = ta.ema(df['Close'], length=50)
            df['EMA_200'] = ta.ema(df['Close'], length=200)
            df['RSI'] = ta.rsi(df['Close'], length=14)
            df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            
            last = df.iloc[-1]
            
            # Cek apakah EMA 200 berhasil dihitung (tidak NaN/Kosong)
            if pd.isna(last['EMA_200']):
                continue

            avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
            
            # Logika Sinyal
            is_uptrend = last['Close'] > last['EMA_200']
            rsi_valid = 40 < last['RSI'] < 70
            whale_detected = last['Volume'] > (1.5 * avg_vol)
            
            signal = "NEUTRAL"
            if is_uptrend and rsi_valid:
                if whale_detected: 
                    signal = "STRONG BUY"
                elif last['Close'] > last['EMA_50']: 
                    signal = "BUY DIP" 
            
            # Risk Calculation
            atr = last['ATR']
            sl = last['Close'] - (2 * atr)
            tp = last['Close'] + (4 * atr)
            dist_sl = (last['Close'] - sl) / last['Close']
            risk_amt = modal_awal * (resiko_per_trade / 100)
            size = risk_amt / dist_sl if dist_sl > 0 else 0
            
            data_row = {
                "Coin": symbol, 
                "Price": last['Close'], 
                "Signal": signal,
                "RSI": round(last['RSI'], 2), 
                "Whale": "YES" if whale_detected else "-",
                "TP": round(tp, 4), 
                "SL": round(sl, 4), 
                "Size ($)": round(size, 2)
            }
            laporan_data.append(data_row)
            
            if signal == "STRONG BUY":
                strong_buy_list.append(data_row)
                
        except Exception as e:
            if len(symbols) == 1:
                st.error(f"Error {symbol}: {str(e)}")
            continue

    if len(symbols) > 1 and status_text:
        status_text.empty()
        progress_bar.empty()
    
    # Telegram Logic
    if kirim_laporan and strong_buy_list and len(symbols) > 1:
        current_signals = sorted([x['Coin'] for x in strong_buy_list])
        last_signals = sorted(st.session_state['last_signals'])
        
        if current_signals != last_signals:
            pesan = f"🦅 *SINYAL PAUS DETECTED* 🦅\n⏰ {datetime.now().strftime('%H:%M')} WIB\n\n"
            for item in strong_buy_list:
                pesan += f"🚀 *{item['Coin']}*\nHarga: {item['Price']}\nSL: {item['SL']} | TP: {item['TP']}\n\n"
            send_telegram(pesan)
            st.session_state['last_signals'] = current_signals
    
    st.session_state['last_scan_time'] = datetime.now().strftime("%H:%M:%S")
    return pd.DataFrame(laporan_data)

# --- DATABASE KOIN ---
all_coins = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT", "FLOKI/USDT",
    "RNDR/USDT", "FET/USDT", "GRT/USDT", "TAO/USDT", "NEAR/USDT", "FIL/USDT",
    "SUI/USDT", "SEI/USDT", "APT/USDT", "INJ/USDT", "TIA/USDT", "ARB/USDT", "OP/USDT",
    "LINK/USDT", "AVAX/USDT", "MATIC/USDT", "UNI/USDT", "LDO/USDT", "AAVE/USDT",
    "LTC/USDT", "BCH/USDT", "TRX/USDT", "DOT/USDT", "ATOM/USDT"
]

# --- SIDEBAR UTAMA ---
with st.sidebar:
    st.header("🦅 MENU JATMIKO")
    
    mode = st.radio("Pilih Mode:", ["🔍 Cek Satu Koin", "📋 Manual Scan (Banyak)", "🤖 Auto Pilot"])
    
    st.divider()
    
    final_symbols = []
    
    if mode == "🔍 Cek Satu Koin":
        st.info("Mode ini untuk analisa cepat 1 koin spesifik.")
        single_coin = st.text_input("Ketik Simbol Koin:", value="BTC/USDT", placeholder="Contoh: PEPE/USDT")
        single_coin = single_coin.upper().strip()
        if single_coin:
            final_symbols = [single_coin]
    else:
        selected_defaults = st.multiselect("Pilih dari Daftar Populer:", options=all_coins, default=all_coins)
        with st.expander("➕ Tambah Koin Lain"):
            custom_input = st.text_area("Pisahkan koma:", placeholder="TURBO/USDT, NEIRO/USDT")
        
        custom_symbols = [s.strip().upper() for s in custom_input.split(',') if s.strip()]
        final_symbols = list(set(selected_defaults + custom_symbols))
        
        if mode == "🤖 Auto Pilot":
            interval = st.select_slider("Refresh (Menit):", options=[15, 30, 60], value=30)
            
    st.divider()
    
    # Pilih Gate.io karena sudah terbukti sukses di tes koneksi
    exchange_id = st.selectbox("Exchange:", ["gateio", "okx"])
    timeframe = st.selectbox("Timeframe:", ["15m", "1h", "4h"])
    modal_awal = st.number_input("Modal ($)", 100.0)
    resiko = st.slider("Resiko (%)", 1, 5, 2)
    
    if mode != "🔍 Cek Satu Koin":
        kirim_laporan = st.checkbox("Kirim Telegram", value=True)
    else:
        kirim_laporan = False 

# --- HALAMAN UTAMA ---
st.title(f"Radar Jatmiko: {exchange_id.upper()}")
st.write(f"🕒 Data Time: **{st.session_state['last_scan_time'] if st.session_state['last_scan_time'] else '-'}**")

df_result = pd.DataFrame()

# ================================
# EKSKUSI BERDASARKAN MODE
# ================================

# Limit candle dinaikkan jadi 300 agar EMA 200 bisa dihitung
LIMIT_CANDLE = 300 

if mode == "🔍 Cek Satu Koin":
    if st.button("🔎 ANALISA SEKARANG", type="primary"):
        if not final_symbols:
            st.error("Masukkan simbol koin dulu!")
        else:
            with st.spinner(f"Menganalisa {final_symbols[0]} di {exchange_id}..."):
                df_result = run_scanner(exchange_id, timeframe, LIMIT_CANDLE, final_symbols, modal_awal, resiko, False)
                
                if not df_result.empty:
                    data = df_result.iloc[0]
                    color = "green" if data['Signal'] == "STRONG BUY" else "orange" if data['Signal'] == "BUY DIP" else "gray"
                    st.markdown(f":{color}[### Hasil: {data['Signal']}]")
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Harga", data['Price'])
                    c2.metric("RSI", data['RSI'])
                    c3.metric("Whale?", data['Whale'])
                    
                    st.divider()
                    st.write("📋 **Rencana Trading:**")
                    st.table(pd.DataFrame([data]))
                else:
                    st.warning(f"Tidak ada data untuk {final_symbols[0]}. Pastikan simbol benar dan Exchange {exchange_id} mendukung.")

elif mode == "📋 Manual Scan (Banyak)":
    if st.button("🚀 SCAN SEMUA LIST", type="primary"):
        if not final_symbols:
            st.error("Pilih koin dulu di sidebar!")
        else:
            with st.spinner("Sedang memata-matai pasar..."):
                df_result = run_scanner(exchange_id, timeframe, LIMIT_CANDLE, final_symbols, modal_awal, resiko, kirim_laporan)
                
                if not df_result.empty:
                    strong = df_result[df_result['Signal'] == "STRONG BUY"]
                    dip = df_result[df_result['Signal'] == "BUY DIP"]
                    neutral = df_result[df_result['Signal'] == "NEUTRAL"]
                    
                    t1, t2, t3 = st.tabs(["🔥 STRONG BUY", "📉 BUY DIP", "😐 NEUTRAL"])
                    with t1:
                        if not strong.empty: st.dataframe(strong, use_container_width=True)
                        else: st.info("Kosong.")
                    with t2: st.dataframe(dip, use_container_width=True)
                    with t3: st.dataframe(neutral, use_container_width=True)

elif mode == "🤖 Auto Pilot":
    c1, c2 = st.columns(2)
    if c1.button("▶️ START LOOP"):
        st.session_state['is_running'] = True
        st.rerun()
    if c2.button("⏹️ STOP LOOP"):
        st.session_state['is_running'] = False
        st.rerun()
        
    if st.session_state['is_running']:
        if not final_symbols:
            st.error("Pilih koin dulu!")
            st.session_state['is_running'] = False
        else:
            st.success("Scanner Berjalan Otomatis.")
            df_result = run_scanner(exchange_id, timeframe, LIMIT_CANDLE, final_symbols, modal_awal, resiko, kirim_laporan)
            
            if not df_result.empty:
                strong = df_result[df_result['Signal'] == "STRONG BUY"]
                if not strong.empty: st.dataframe(strong, use_container_width=True)
                else: st.info("Belum ada Strong Buy di putaran ini.")
            
            timer = st.empty()
            for s in range(interval * 60, 0, -1):
                if not st.session_state['is_running']: break
                m, sc = divmod(s, 60)
                timer.metric("Next Scan:", f"{m:02d}:{sc:02d}")
                time.sleep(1)
            
            if st.session_state['is_running']: st.rerun()
