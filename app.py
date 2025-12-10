import streamlit as st
import ccxt
import pandas as pd
import time
import numpy as np

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Jatmiko Institutional Hunter",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stDataFrame { font-size: 1.0rem; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. RUMUS MANUAL (MATEMATIKA TRADING) ---

def hitung_rsi_manual(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def hitung_ema_manual(series, period):
    return series.ewm(span=period, adjust=False).mean()

def hitung_atr_manual(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# --- 3. FITUR BARU: AMT & CVD LOGIC ---

def hitung_poc_volume_profile(df, bins=30):
    """
    Auction Market Theory (AMT): Mencari POC (Point of Control)
    Harga di mana volume transaksi paling banyak terjadi.
    """
    try:
        # Buat range harga dari Low terendah sampai High tertinggi
        price_range = np.linspace(df['low'].min(), df['high'].max(), bins)
        
        # Kelompokkan volume ke dalam range harga (Bucket)
        # Kita pakai pendekatan sederhana: Volume candle dialokasikan ke harga Close-nya
        df['bucket'] = pd.cut(df['close'], bins=price_range, labels=price_range[:-1])
        
        # Hitung total volume per harga
        profile = df.groupby('bucket')['volume'].sum()
        
        # Cari harga dengan volume tertinggi (POC)
        poc_price = profile.idxmax() 
        return float(poc_price)
    except:
        return df['close'].mean() # Fallback jika gagal

def hitung_cvd_approx(df):
    """
    Cumulative Volume Delta (CVD) Approximation
    Menghitung tekanan Beli vs Jual berdasarkan bentuk Candle.
    """
    # Logika: (Close - Open) / (High - Low) * Volume
    # Jika candle hijau tebal = Delta Positif besar
    # Jika candle doji = Delta kecil
    range_candle = df['high'] - df['low']
    range_candle = range_candle.replace(0, 1) # Hindari pembagian nol
    
    delta = ((df['close'] - df['open']) / range_candle) * df['volume']
    
    # Cumulative Sum (Akumulasi)
    cvd = delta.cumsum()
    return cvd

# --- 4. FUNGSI PENGAMBIL DATA ---

@st.cache_data(ttl=300)
def get_top_volume_coins(limit=25):
    try:
        exchange = ccxt.gateio()
        tickers = exchange.fetch_tickers()
        df = pd.DataFrame(tickers).T
        df = df[df['symbol'].str.endswith('/USDT')]
        exclude = ['USDC/USDT', 'DAI/USDT', 'TUSD/USDT', 'USDP/USDT']
        df = df[~df['symbol'].isin(exclude)]
        df = df.sort_values(by='quoteVolume', ascending=False)
        return df['symbol'].head(limit).tolist()
    except:
        return []

def get_instant_top_gainers(limit=5):
    try:
        exchange = ccxt.gateio()
        tickers = exchange.fetch_tickers()
        df = pd.DataFrame(tickers).T
        df = df[df['symbol'].str.endswith('/USDT')]
        df = df.sort_values(by='percentage', ascending=False)
        results = []
        for index, row in df.head(limit).iterrows():
            results.append({
                "Symbol": row['symbol'],
                "Harga": row['last'],
                "Naik %": row['percentage'],
            })
        return pd.DataFrame(results)
    except:
        return pd.DataFrame()

def analyze_market_depth(exchange, symbol):
    try:
        orderbook = exchange.fetch_order_book(symbol, limit=20)
        bids_vol = sum([bid[1] for bid in orderbook['bids']])
        asks_vol = sum([ask[1] for ask in orderbook['asks']])
        if asks_vol == 0: return 1.0
        return bids_vol / asks_vol
    except:
        return 1.0

def get_market_signal(symbol, timeframe, modal_user, risk_pct):
    try:
        exchange = ccxt.gateio()
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        if not bars: return None
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if len(df) < 50: return None

        # --- DATA PROCESSING ---
        whale_ratio = analyze_market_depth(exchange, symbol)
        
        # Indikator Dasar
        df['RSI'] = hitung_rsi_manual(df['close'], 14)
        df['EMA_200'] = hitung_ema_manual(df['close'], 200)
        df['ATR'] = hitung_atr_manual(df, 14)
        
        # --- ADVANCED INDICATORS (AMT & CVD) ---
        poc_price = hitung_poc_volume_profile(df)
        df['CVD'] = hitung_cvd_approx(df)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- SCORING SYSTEM (REVISI INSTITUSI) ---
        score = 0
        reasons = []
        status = "NEUTRAL"
        
        # 1. Auction Market Theory (POC)
        # Jika Harga di atas POC = Bullish Control
        if last['close'] > poc_price:
            score += 2
            reasons.append("Harga > POC (Dominasi Buyer)")
        else:
            score -= 2
            reasons.append("Harga < POC (Dominasi Seller)")

        # 2. CVD Slope (Tren Delta)
        # Apakah tekanan beli meningkat dibanding candle sebelumnya?
        if last['CVD'] > prev['CVD']:
            score += 1
            # reasons.append("CVD Naik") # Terlalu penuh kalau ditampilkan
        else:
            score -= 1
            
        # 3. Whale Order Book
        is_whale = False
        if whale_ratio >= 2.0:
            score += 3; reasons.append(f"🐳 WHALE ({whale_ratio:.1f}x)")
            is_whale = True
        elif whale_ratio <= 0.5: score -= 3

        # 4. Pump Detector (Volume Spike)
        vol_ma = df['volume'].rolling(20).mean().iloc[-1]
        if last['volume'] > (vol_ma * 3) and last['close'] > last['open']:
            score += 5; reasons.append("🚀 VOL SPIKE"); status = "🚀 MELEDAK"

        # 5. RSI & Trend
        if last['RSI'] < 30: score += 2; reasons.append("Oversold")
        elif last['RSI'] > 70 and not is_whale: score -= 2
        
        if last['close'] > last['EMA_200']: score += 1

        # Status Final
        if score >= 6: status = "💎 INSTI-PUMP"
        elif score >= 3: status = "STRONG BUY"
        elif score >= 1: status = "BUY"
        elif score <= -3: status = "STRONG SELL"
        elif score <= -1: status = "SELL"
        
        # --- MONEY MANAGEMENT ---
        entry_price = last['close']
        atr_val = last['ATR'] if pd.notnull(last['ATR']) else (entry_price * 0.02)
        
        risk_amount = (modal_user * risk_pct) / 100
        stop_loss = 0
        take_profit = 0
        pos_size_usdt = 0
        
        if score > 0: # Setup BUY
            # SL ditaruh sedikit di bawah POC (Support Kuat) atau ATR
            stop_loss = min(entry_price - (2 * atr_val), poc_price * 0.99)
            dist_sl = entry_price - stop_loss
            take_profit = entry_price + (dist_sl * 2) # RR 1:2
            
            if dist_sl > 0:
                coin_qty = risk_amount / dist_sl
                pos_size_usdt = coin_qty * entry_price
        
        if pos_size_usdt > modal_user: pos_size_usdt = modal_user 
        
        link = f"https://www.coinglass.com/currencies/{symbol.split('/')[0]}"

        return {
            "Symbol": symbol,
            "Price": entry_price,
            "Score": score,
            "Signal": status,
            "POC": poc_price, # Harga Wajar
            "CVD Trend": "↗️ NAIK" if last['CVD'] > prev['CVD'] else "↘️ TURUN",
            "ENTRY": entry_price,
            "STOP LOSS": stop_loss,
            "TAKE PROFIT": take_profit,
            "BELI ($)": round(pos_size_usdt, 2),
            "Alasan": ", ".join(reasons),
            "Info": link
        }
    except:
        return None

# --- 5. SIDEBAR ---
st.sidebar.title("💰 Money Management")
modal_user = st.sidebar.number_input("Modal ($):", value=1000, step=100)
risk_pct = st.sidebar.slider("Resiko (%):", 1, 5, 2)
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Scanner")
scan_mode = st.sidebar.radio("Target:", ["📋 Manual List", "🤖 Auto Top 25", "🔍 Cari Koin", "📄 Paste Coinglass"])

input_text = ""
if scan_mode == "🔍 Cari Koin": input_text = st.sidebar.text_input("Simbol:", placeholder="GALA")
elif scan_mode == "📄 Paste Coinglass": input_text = st.sidebar.text_area("Daftar:", placeholder="BTC ETH SOL")

MANUAL_WATCHLIST = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PEPE/USDT', 'DOGE/USDT', 'GALA/USDT', 'XRP/USDT', 'SUI/USDT']

# --- 6. TAMPILAN UTAMA ---
st.title("🦅 Jatmiko Institutional Hunter")
st.markdown("Fitur: **CVD Approximation** • **Auction Market Theory (POC)** • **Whale Radar**")

col1, col2 = st.columns([1, 4])
tf = col1.selectbox("Timeframe", ["15m", "1h", "4h"], index=0)

if col2.button("🚀 ANALISA INSTITUSI", use_container_width=True):
    
    target_coins = []
    if scan_mode == "📋 Manual List": target_coins = MANUAL_WATCHLIST
    elif scan_mode == "🤖 Auto Top 25": 
        with st.spinner("Mengambil Data Pasar..."): target_coins = get_top_volume_coins(25)
    elif scan_mode == "🔍 Cari Koin": 
        if input_text: target_coins = [input_text.upper().strip() + "/USDT"]
    elif scan_mode == "📄 Paste Coinglass":
        if input_text:
            raw = input_text.replace('\n', ' ').replace(',', ' ').split(' ')
            target_coins = [x.strip().upper() + "/USDT" for x in raw if x.strip()]
            target_coins = list(set(target_coins))

    if not target_coins:
        st.error("Target kosong.")
    else:
        results = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, coin in enumerate(target_coins):
            bar.progress((i + 1)/len(target_coins))
            status.caption(f"Menghitung Volume Profile: **{coin}**")
            data = get_market_signal(coin, tf, modal_user, risk_pct)
            if data: results.append(data)
            time.sleep(0.1)
            
        bar.empty(); status.empty()
        
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values(by='Score', ascending=False)
            
            # CONFIG TABEL
            cfg = {
                "Info": st.column_config.LinkColumn("Audit"),
                "Price": st.column_config.NumberColumn("Harga", format="%.4f"),
                "POC": st.column_config.NumberColumn("Harga Wajar (POC)", format="%.4f", help="Point of Control: Harga dengan volume transaksi terbanyak"),
                "ENTRY": st.column_config.NumberColumn("Entry", format="%.4f"),
                "STOP LOSS": st.column_config.NumberColumn("Stop Loss", format="%.4f"),
                "TAKE PROFIT": st.column_config.NumberColumn("Take Profit", format="%.4f"),
                "BELI ($)": st.column_config.NumberColumn("Posisi Size", format="$ %.2f"),
                "Score": st.column_config.ProgressColumn("Skor", min_value=-5, max_value=8, format="%d"),
            }
            
            tab1, tab2 = st.tabs(["💎 SETUP INSTITUSI", "📋 DATA MENTAH"])
            
            with tab1:
                df_buy = df[df['Score'] > 0]
                if not df_buy.empty:
                    st.balloons()
                    st.success("Setup Trading dengan AMT & CVD Konfirmasi")
                    # Kolom Prioritas
                    cols = ["Symbol", "Signal", "POC", "CVD Trend", "ENTRY", "STOP LOSS", "TAKE PROFIT", "BELI ($)", "Alasan"]
                    st.dataframe(df_buy[cols], use_container_width=True, hide_index=True, column_config=cfg)
                else:
                    st.warning("Belum ada setup yang memenuhi kriteria Institusi.")
                    st.dataframe(get_instant_top_gainers(), use_container_width=True)

            with tab2:
                st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg)
        else:
            st.error("Gagal ambil data.")