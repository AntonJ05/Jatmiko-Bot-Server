import ccxt

print("--- SEDANG MENCOBA MENGHUBUNGI GATE.IO ---")
print("Mohon tunggu sebentar...")

try:
    # Coba konek ke Gate.io
    exchange = ccxt.gateio()
    # Minta data ticker (daftar harga)
    tickers = exchange.fetch_tickers()
    
    print("\n✅ SUKSES! INTERNET AMAN.")
    print(f"Berhasil mengambil data {len(tickers)} koin.")

except Exception as e:
    print("\n❌ GAGAL TERHUBUNG!")
    print("Kemungkinan besar akses diblokir oleh Internet Provider Anda.")
    print(f"Pesan Error: {e}")

input("\nTekan ENTER untuk keluar...")