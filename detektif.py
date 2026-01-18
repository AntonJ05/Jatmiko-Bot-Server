import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np

print("--- MULAI DIAGNOSA ---")
print(f"Versi Python Anda: {pd.__version__} (Pandas)")
print(f"Versi Numpy Anda: {np.__version__}")

try:
    print("\n1. Menghubungi Gate.io...")
    exchange = ccxt.gateio()
    
    print("2. Mengambil Candle BTC/USDT...")
    bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=50)
    
    if not bars:
        print("❌ GAGAL: Data Candle Kosong!")
    else:
        print(f"✅ SUKSES: Dapat {len(bars)} candle.")
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        print("\n3. Mencoba Menghitung RSI (Pandas-TA)...")
        # Ini bagian yang sering error kalau versi numpy tidak cocok
        df['RSI'] = df.ta.rsi(length=14)
        print(f"✅ SUKSES HITUNG RSI! Nilai terakhir: {df['RSI'].iloc[-1]}")
        
except Exception as e:
    print("\n❌ DITEMUKAN ERROR FATAL!")
    print("Tolong fotokan pesan error di bawah ini:")
    print("-" * 30)
    print(e)
    print("-" * 30)
    import traceback
    traceback.print_exc()

input("\nTekan ENTER untuk keluar...")