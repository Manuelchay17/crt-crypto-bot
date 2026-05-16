import pandas as pd
import datetime
import requests
import os

# --- CONFIG GITHUB SECRETS ---
# --- CONFIG GITHUB SECRETS ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# Daftar 30 Koin Crypto Utama
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
    "NEARUSDT", "ATOMUSDT", "LTCUSDT", "BCHUSDT", "TRXUSDT",
    "APTUSDT", "SUIUSDT", "OPUSDT", "ARBUSDT", "INJUSDT",
    "TIAUSDT", "RNDRUSDT", "FETUSDT", "FILUSDT", "ICPUSDT",
    "LDOUSDT", "STXUSDT", "DOGEUSDT", "SHIBUSDT", "PEPEUSDT"
]

# Definisi 3 Alignment Sesuai Request di Awal
ALIGNMENTS = [
    {"htf": "1h", "ltf": "15m", "nama": "1H - 15M (Scalping)"},
    {"htf": "4h", "ltf": "1h",  "nama": "4H - 1H (Intraday)"},
    {"htf": "1d", "ltf": "4h",  "nama": "Daily - 4H (Swing)"}
]

def kirim_notifikasi_telegram(pesan):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Error kirim telegram:", e)

def get_binance_data(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        float_cols = ['open', 'high', 'low', 'close', 'volume']
        df[float_cols] = df[float_cols].astype(float)
        return df
    except Exception as e:
        print(f"Gagal ambil data {symbol} {interval}: {e}")
        return pd.DataFrame()

def hitung_bias_ict(df):
    """Menentukan Bias pada HTF (Candle Swept atau Body Break)"""
    if df.empty or len(df) < 15: 
        return "NEUTRAL"
    
    prev = df.iloc[-2] # Candle yang baru saja close sah
    
    # Range acuan untuk mencari liquidity pool terdekat (15 candle terakhir)
    highest_range = df['high'].iloc[-15:-2].max()
    lowest_range = df['low'].iloc[-15:-2].min()
    
    # 1. Model Candle Swept Liquidity
    if prev['low'] < lowest_range and prev['close'] > lowest_range:
        return "BULLISH"
    if prev['high'] > highest_range and prev['close'] < highest_high:
        return "BEARISH"
        
    # 2. Model Body Break (Market Structure Shift)
    if prev['close'] > highest_range:
        return "BULLISH"
    if prev['close'] < lowest_range:
        return "BEARISH"
        
    return "NEUTRAL"

def deteksi_crt_swept_ltf(df, bias):
    """Logika Candle Range Theory (CRT) / Swept Candle di Timeframe Kanan (LTF)"""
    if len(df) < 3: 
        return False
    
    current_candle = df.iloc[-1] # Candle LTF berjalan/terbaru yang baru close
    prev_candle = df.iloc[-2]    # Candle LTF sebelumnya (Range CRT)
    
    if bias == "BULLISH":
        # CRT Bullish: Candle terbaru memanipulasi (Swept) LOW candle sebelumnya, 
        # lalu close berbalik naik di atas LOW candle sebelumnya tersebut.
        if current_candle['low'] < prev_candle['low'] and current_candle['close'] > prev_candle['low']:
            return True
            
    elif bias == "BEARISH":
        # CRT Bearish: Candle terbaru memanipulasi (Swept) HIGH candle sebelumnya, 
        # lalu close berbalik turun di bawah HIGH candle sebelumnya tersebut.
        if current_candle['high'] > prev_candle['high'] and current_candle['close'] < prev_candle['high']:
            return True
            
    return False

def cek_fvg_atau_swing_ltf(df):
    """Filter Probabilitas: Mendeteksi apakah CRT bersandar di FVG atau Swing High/Low"""
    if len(df) < 5: 
        return False
        
    c1 = df.iloc[-3]
    c3 = df.iloc[-1]
    
    # Cari Fair Value Gap (FVG)
    fvg_bullish = c3['low'] > c1['high']
    fvg_bearish = c3['high'] < c1['low']
    
    # Cari area ekstrem Swing Terdekat (20 candle terakhir)
    lokal_low = df['low'].tail(20).min()
    lokal_high = df['high'].tail(20).max()
    
    # Toleransi kedekatan harga (0.15%)
    dekat_swing_low = abs(c3['close'] - lokal_low) / lokal_low < 0.0015
    dekat_swing_high = abs(c3['close'] - lokal_high) / lokal_high < 0.0015
    
    return fvg_bullish or fvg_bearish or dekat_swing_low or dekat_swing_high

def jalankan_bot():
    print(f"🚀 Memulai Pemindaian Multi-Timeframe ({len(WATCHLIST)} Koin)...")
    
    for market in WATCHLIST:
        for align in ALIGNMENTS:
            # Mengambil data dinamis sesuai settingan aligment masing-masing
            df_htf = get_binance_data(market, interval=align["htf"])
            df_ltf = get_binance_data(market, interval=align["ltf"])
            
            if df_htf.empty or df_ltf.empty: 
                continue
                
            # 1. Cek Bias HTF (Sisi Kiri)
            bias_htf = hitung_bias_ict(df_htf)
            if bias_htf == "NEUTRAL": 
                continue
                
            # 2. Cek Keselarasan Bias LTF (Sisi Kanan)
            bias_ltf = hitung_bias_ict(df_ltf)
            
            # Aturan: Bias HTF dan LTF harus selaras (Sama-sama Bullish / Bearish)
            if bias_htf == bias_ltf:
                
                # 3. Cari Apakah ada Pemicu CRT / Swept Candle di LTF
                if deteksi_crt_swept_ltf(df_ltf, bias_htf):
                    
                    # 4. Filter High Probability (Jika di dalam FVG / Swing)
                    is_high_prob = cek_fvg_atau_swing_ltf(df_ltf)
                    status_prob = "🔥 HIGH PROBABILITY (FVG / Swing Re-test)" if is_high_prob else "⚠️ LOW PROBABILITY (Middle Zone)"
                    
                    # Kirim Sinyal Spesifik ke Telegram
                    pesan = (
                        f"🎯 *CANDLE RANGE THEORY (CRT) SIGNAL* 🎯\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *Asset:* #{market}\n"
                        f"📐 *Alignment:* {align['nama']}\n"
                        f"📈 *Daily Bias:* {bias_htf}\n"
                        f"🌀 *Trigger:* Swept Candle CRT Valid\n"
                        f"🛡️ *Klasifikasi:* {status_prob}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏰ *Waktu:* {datetime.datetime.utcnow().strftime('%H:%M')} UTC"
                    )
                    kirim_notifikasi_telegram(pesan)
                    
    print("✅ Semua koin dan semua pasangan TF selesai di-scan.")

if __name__ == "__main__":
    jalankan_bot()