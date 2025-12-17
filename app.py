import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Jatmiko Hybrid Pro", page_icon="🦅", layout="wide")

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
    significant_signals = [] 
    
    progress_bar = None
    status_text = None
    if len(symbols) > 1:
        status_text = st.empty()
        progress_bar = st.progress(0)
    
    total_symbols = len(symbols)
    
    for i, symbol in enumerate(symbols):
        if len(symbols) > 1 and progress_bar:
            try:
                progress_percent = (i + 1) / total_symbols
                progress_bar.progress(progress_percent)
                status_text.text(f"🦅 Menganalisa Pola Candle {symbol} ({i+1}/{total_symbols})...")
            except: pass
        
        try:
            # 1. AMBIL DATA
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit_candle)
            if not bars: continue

            df = pd.DataFrame(bars, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['Time'] = pd.to_datetime(df['Time'], unit='ms')

            df.set_index('Time', inplace=True)
            df.sort_index(inplace=True) 

            if len(df) < 200: continue
            
            # 2. HITUNG INDIKATOR TREND (Jatmiko Logic)
            df['EMA_50'] = ta.ema(df['Close'], length=50)
            df['EMA_200'] = ta.ema(df['Close'], length=200)
            df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
            df['RSI'] = ta.rsi(df['Close'], length=14)
            df['MFI'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
            df['ADX'] = ta.adx(df['High'], df['Low'], df['Close'])['ADX_14']
            df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            
            # Rata-rata Volume untuk deteksi Paus
            df['VOL_SMA'] = df['Volume'].rolling(20).mean()

            # --- PERHITUNGAN MANUAL (GainzAlgo Logic) ---
            # Kita hitung manual karena kita butuh logika Candle Engulfing + Stability
            
            last = df.iloc[-1]   # Candle Sekarang
            prev = df.iloc[-2]   # Candle Sebelumnya

            if pd.isna(last['EMA_200']) or pd.isna(last['VWAP']): continue

            # A. Stability Index (Dari Script Teman)
            # Rumus: (Close - Open) / (High - Low)
            # Tujuannya menyaring candle "kurus" atau Doji
            body_size = abs(last['Close'] - last['Open'])
            total_range = last['High'] - last['Low']
            
            stability_index = 0
            if total_range > 0:
                stability_index = body_size / total_range
            
            # Kita pakai 0.5 (Essential Mode) agar tidak terlalu ketat, tapi cukup memfilter noise
            is_stable_candle = stability_index > 0.5

            # B. Engulfing Pattern (Dari Script Teman)
            # Bullish Engulfing: Kemarin Merah, Sekarang Hijau & Lebih Besar
            bullish_engulfing = (prev['Close'] < prev['Open']) and \
                                (last['Close'] > last['Open']) and \
                                (last['Close'] > prev['Open']) and \
                                (last['Open'] < prev['Close'])

            # Bearish Engulfing: Kemarin Hijau, Sekarang Merah & Lebih Besar
            bearish_engulfing = (prev['Close'] > prev['Open']) and \
                                (last['Close'] < last['Open']) and \
                                (last['Close'] < prev['Open']) and \
                                (last['Open'] > prev['Close'])

            # 3. LOGIKA GABUNGAN (HYBRID)
            
            # Jatmiko Logic (Trend & Filter)
            is_uptrend = last['Close'] > last['EMA_200']
            is_downtrend = last['Close'] < last['EMA_200']
            above_vwap = last['Close'] > last['VWAP']
            below_vwap = last['Close'] < last['VWAP']
            strong_trend = last['ADX'] > 20 # Standar 20 cukup karena sudah ada filter candle
            
            # Whale Logic
            whale_vol_spike = last['Volume'] > (2.0 * last['VOL_SMA']) # 2x Volume

            signal = "NEUTRAL"
            reason = "-"
            pola_candle = "-"

            # --- SKENARIO BUY HYBRID ---
            # Syarat: Trend Naik + Diatas VWAP + (Ada Engulfing ATAU Paus) + Candle Stabil
            if is_uptrend and above_vwap and strong_trend:
                if last['RSI'] < 70:
                    # Prioritas 1: Pola Candle Engulfing yang Stabil
                    if bullish_engulfing and is_stable_candle:
                        signal = "STRONG BUY"
                        pola_candle = "🕯️ Bullish Engulfing"
                        reason = "Trend Up + Engulfing Valid"
                    
                    # Prioritas 2: Ada Paus Masuk (Walau ga engulfing, tapi volume meledak)
                    elif whale_vol_spike and is_stable_candle:
                        signal = "STRONG BUY"
                        pola_candle = "🐋 Whale Pump"
                        reason = "Trend Up + Whale Volume"
                    
                    # Prioritas 3: Pullback Biasa (Tanpa Engulfing) - Kita kasih label "BUY DIP"
                    elif last['Close'] > last['EMA_50'] and stability_index > 0.4:
                        signal = "BUY DIP"
                        reason = "Trend Up (Waiting Confirmation)"
                else:
                    reason = "Overbought"
            
            # --- SKENARIO SELL HYBRID ---
            elif is_downtrend and below_vwap and strong_trend:
                if last['RSI'] > 30:
                    if bearish_engulfing and is_stable_candle:
                        signal = "STRONG SELL"
                        pola_candle = "🕯️ Bearish Engulfing"
                        reason = "Trend Down + Engulfing Valid"
                    
                    elif whale_vol_spike and is_stable_candle:
                        signal = "STRONG SELL"
                        pola_candle = "🐋 Whale Dump"
                        reason = "Trend Down + Whale Volume"
                        
                    elif last['Close'] < last['EMA_50'] and stability_index > 0.4:
                        signal = "SELL RALLY"
                        reason = "Trend Down (Waiting Confirmation)"
                else:
                    reason = "Oversold"

            # 4. ENTRY TRIGGER & SAFETY SL
            entry_trigger_price = 0
            confirm_status = "-"
            
            # Logic Trigger mengikuti pola candle
            if "BUY" in signal:
                # Jika Engulfing, entry-nya di harga Close candle ini (Market Exec)
                if "Engulfing" in pola_candle:
                    entry_trigger_price = last['Close']
                    confirm_status = "✅ EXECUTE NOW"
                else:
                    # Jika bukan engulfing, tunggu tembus High kemarin
                    entry_trigger_price = prev['High']
                    confirm_status = "✅ RUNNING" if last['Close'] > entry_trigger_price else "⏳ PENDING"

            elif "SELL" in signal:
                if "Engulfing" in pola_candle:
                    entry_trigger_price = last['Close']
                    confirm_status = "✅ EXECUTE NOW"
                else:
                    entry_trigger_price = prev['Low']
                    confirm_status = "✅ RUNNING" if last['Close'] < entry_trigger_price else "⏳ PENDING"
            
            # 5. MANAJEMEN RESIKO
            atr = last['ATR']
            base_price = last['Close'] # Base price selalu harga sekarang untuk hitungan dinamis
            
            # Safety SL
            dist_atr = 2 * atr
            dist_min = base_price * 0.01 
            final_dist = max(dist_atr, dist_min)
            
            if "BUY" in signal:
                sl = base_price - final_dist
                tp = base_price + (final_dist * 1.5)
                dist_sl_percent = (base_price - sl) / base_price
            elif "SELL" in signal:
                sl = base_price + final_dist
                tp = base_price - (final_dist * 1.5)
                dist_sl_percent = (sl - base_price) / base_price
            else:
                sl = 0; tp = 0; dist_sl_percent = 0

            # Hitung Size
            risk_amt_usd = modal_awal * (resiko_per_trade / 100)
            position_size_usd = 0
            leverage_needed = 1
            margin_needed = 0

            if dist_sl_percent > 0:
                position_size_usd = risk_amt_usd / dist_sl_percent
                leverage_raw = position_size_usd / modal_awal
                leverage_needed = max(1, round(leverage_raw))
                margin_needed = position_size_usd / leverage_needed

            data_row = {
                "Coin": symbol, 
                "Price": float(f"{last['Close']:.8f}"), 
                "Signal": signal,
                "Pattern": pola_candle,
                "Status": confirm_status,
                "Stability": f"{int(stability_index * 100)}%", # Tampilkan kualitas candle
                "Trigger ($)": float(f"{entry_trigger_price:.8f}"), 
                "TP": float(f"{tp:.8f}"), 
                "SL": float(f"{sl:.8f}"), 
                "Total Size ($)": round(position_size_usd, 2),
                "Est. Margin ($)": round(margin_needed, 2),
                "Lev (x)": f"{leverage_needed}x",
                "Info": reason
            }
            laporan_data.append(data_row)
            
            if "STRONG" in signal:
                significant_signals.append(data_row)
                
        except Exception as e:
            if len(symbols) == 1: st.error(f"Error {symbol}: {str(e)}")
            continue

    if len(symbols) > 1 and status_text:
        status_text.empty()
        progress_bar.empty()
    
    # Telegram Logic
    if kirim_laporan and significant_signals and len(symbols) > 1:
        current_sig_str = sorted([f"{x['Coin']}_{x['Signal']}_{x['Pattern']}" for x in significant_signals])
        last_sig_str = sorted(st.session_state['last_signals'])
        
        if current_sig_str != last_sig_str:
            pesan = f"🦅 *JATMIKO HYBRID SIGNAL* 🦅\n⏰ {datetime.now().strftime('%H:%M')} WIB\n\n"
            for item in significant_signals:
                icon = "🟢" if "BUY" in item['Signal'] else "🔴"
                
                pesan += f"{icon} *{item['Coin']}* ({item['Signal']})\n"
                pesan += f"🔥 Pola: {item['Pattern']} (Kualitas: {item['Stability']})\n"
                pesan += f"Lev: {item['Lev (x)']} | Margin: ${item['Est. Margin ($)']}\n"
                pesan += f"🎯 TP: {item['TP']:.8f}\n🛑 SL: {item['SL']:.8f}\n\n"
            
            send_telegram(pesan)
            st.session_state['last_signals'] = current_sig_str
    
    st.session_state['last_scan_time'] = datetime.now().strftime("%H:%M:%S")
    return pd.DataFrame(laporan_data)

# --- LIST KOIN ---
all_coins = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT", "FLOKI/USDT",
    "RNDR/USDT", "FET/USDT", "GRT/USDT", "TAO/USDT", "NEAR/USDT", "FIL/USDT",
    "SUI/USDT", "SEI/USDT", "APT/USDT", "INJ/USDT", "TIA/USDT", "ARB/USDT", "OP/USDT",
    "LINK/USDT", "AVAX/USDT", "MATIC/USDT", "UNI/USDT", "LDO/USDT", "AAVE/USDT",
    "LTC/USDT", "BCH/USDT", "TRX/USDT", "DOT/USDT", "ATOM/USDT"
]

# --- SIDEBAR ---
with st.sidebar:
    st.header("🦅 JATMIKO HYBRID")
    mode = st.radio("Mode:", ["🔍 Single Analyzer", "📋 Bulk Scanner", "🤖 Auto Pilot"])
    st.divider()
    
    final_symbols = []
    if mode == "🔍 Single Analyzer":
        st.info("Cek detail Pattern & Stability.")
        single_coin = st.text_input("Simbol:", value="BTC/USDT")
        if single_coin: final_symbols = [single_coin.upper().strip()]
    else:
        selected_defaults = st.multiselect("Market:", options=all_coins, default=all_coins)
        with st.expander("➕ Tambah Custom"):
            custom_input = st.text_area("List:", placeholder="TURBO/USDT")
        custom_symbols = [s.strip().upper() for s in custom_input.split(',') if s.strip()]
        final_symbols = list(set(selected_defaults + custom_symbols))
        
        if mode == "🤖 Auto Pilot":
            interval = st.select_slider("Refresh (Menit):", options=[15, 30, 60], value=30)
            
    st.divider()
    exchange_id = st.selectbox("Exchange:", ["gateio", "okx"])
    timeframe = st.selectbox("Timeframe:", ["15m", "1h", "4h"])
    modal_awal = st.number_input("Modal Trading ($)", 100.0)
    resiko = st.slider("Resiko per Trade (%)", 1, 5, 2)
    kirim_laporan = st.checkbox("Telegram", value=True) if mode != "🔍 Single Analyzer" else False

# --- HALAMAN UTAMA ---
st.title(f"Radar Jatmiko: {exchange_id.upper()}")
st.write(f"🕒 Update: **{st.session_state['last_scan_time'] if st.session_state['last_scan_time'] else '-'}**")

LIMIT_CANDLE = 300

if mode == "🔍 Single Analyzer":
    if st.button("🔎 ANALISA", type="primary"):
        if not final_symbols: st.error("Input simbol!")
        else:
            with st.spinner("Mendeteksi Pola Candle Hybrid..."):
                df = run_scanner(exchange_id, timeframe, LIMIT_CANDLE, final_symbols, modal_awal, resiko, False)
                if not df.empty:
                    data = df.iloc[0]
                    color = "green" if "BUY" in data['Signal'] else "red" if "SELL" in data['Signal'] else "gray"
                    st.markdown(f":{color}[## {data['Signal']}]")
                    
                    if "Engulfing" in data['Pattern']:
                        st.success(f"🔥 POLA CANDLE: {data['Pattern']}")
                    elif "Whale" in data['Pattern']:
                         st.warning(f"🐋 VOLUME: {data['Pattern']}")
                    else:
                        st.info("Pola Candle: Biasa")

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Kualitas Candle (Stability)", data['Stability'])
                    c2.metric("Pemicu (Trigger)", f"{data['Trigger ($)']:.8f}")
                    c3.metric("Leverage", data['Lev (x)'])
                    
                    st.divider()
                    st.write(f"ℹ️ **Info:** {data['Info']}")
                    st.subheader("💰 Money Management")
                    st.write(f"Modal (Margin): **${data['Est. Margin ($)']}**")
                    st.table(pd.DataFrame([data]))
                else: st.warning("Data tidak ditemukan.")

elif mode == "📋 Bulk Scanner":
    if st.button("🚀 SCAN", type="primary"):
        if not final_symbols: st.error("Pilih koin!")
        else:
            with st.spinner("Scanning..."):
                df = run_scanner(exchange_id, timeframe, LIMIT_CANDLE, final_symbols, modal_awal, resiko, kirim_laporan)
                if not df.empty:
                    s_buy = df[df['Signal'].str.contains("BUY")]
                    s_sell = df[df['Signal'].str.contains("SELL")]
                    others = df[df['Signal'] == "NEUTRAL"]
                    
                    t1, t2, t3 = st.tabs(["🟢 LONG", "🔴 SHORT", "⚪ NEUTRAL"])
                    st.markdown("<style>td {white-space: nowrap;}</style>", unsafe_allow_html=True)
                    
                    with t1: st.dataframe(s_buy, use_container_width=True)
                    with t2: st.dataframe(s_sell, use_container_width=True)
                    with t3: st.dataframe(others, use_container_width=True)

elif mode == "🤖 Auto Pilot":
    c1, c2 = st.columns(2)
    if c1.button("▶️ START"):
        st.session_state['is_running'] = True
        st.rerun()
    if c2.button("⏹️ STOP"):
        st.session_state['is_running'] = False
        st.rerun()
        
    if st.session_state['is_running']:
        st.success("Hybrid Engine ON.")
        df = run_scanner(exchange_id, timeframe, LIMIT_CANDLE, final_symbols, modal_awal, resiko, kirim_laporan)
        
        if not df.empty:
            s_buy = df[df['Signal'].str.contains("BUY")]
            s_sell = df[df['Signal'].str.contains("SELL")]
            
            c1, c2 = st.columns(2)
            with c1: 
                st.subheader("🟢 Buy")
                if not s_buy.empty: st.dataframe(s_buy)
                else: st.write("-")
            with c2: 
                st.subheader("🔴 Sell")
                if not s_sell.empty: st.dataframe(s_sell)
                else: st.write("-")
        
        timer = st.empty()
        for s in range(interval * 60, 0, -1):
            if not st.session_state['is_running']: break
            m, sc = divmod(s, 60)
            timer.metric("Next Scan:", f"{m:02d}:{sc:02d}")
            time.sleep(1)
        
        if st.session_state['is_running']: st.rerun()
