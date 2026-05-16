import pandas as pd
import datetime
import requests
import os

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

STRUKTUR_SETUP = [
    {"bias_tf": "1h", "crt_tf": "15m", "cisd_tf": "1m",  "nama": "1H-15M-1M (Scalping)"},
    {"bias_tf": "4h", "crt_tf": "1h",  "cisd_tf": "5m",  "nama": "4H-1H-5M (Intraday)"},
    {"bias_tf": "1d", "crt_tf": "4h",  "cisd_tf": "15m", "nama": "Daily-4H-15M (Swing)"}
]

def kirim_notifikasi_telegram(pesan):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except Exception as e: print("Error kirim telegram:", e)

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
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        return pd.DataFrame()

def hitung_bias_htf(df):
    """Menentukan Bias HTF sekaligus mengembalikan alasan teknisnya"""
    if df.empty or len(df) < 15: return "NEUTRAL", ""
    prev = df.iloc[-2]
    highest_range = df['high'].iloc[-15:-2].max()
    lowest_range = df['low'].iloc[-15:-2].min()
    
    # 1. Model Candle Swept Liquidity
    if prev['low'] < lowest_range and prev['close'] > lowest_range: 
        return "BULLISH", "Liquidity Swept (Mengambil Low lama lalu reject naik)"
    if prev['high'] > highest_range and prev['close'] < highest_range: 
        return "BEARISH", "Liquidity Swept (Mengambil High lama lalu reject turun)"
    
    # 2. Model Body Break
    if prev['close'] > highest_range: 
        return "BULLISH", "Market Structure Shift (Body Break ke atas)"
    if prev['close'] < lowest_range: 
        return "BEARISH", "Market Structure Shift (Body Break ke bawah)"
        
    return "NEUTRAL", ""

def cari_cisd_mikro(df_cisd, bias):
    if df_cisd.empty or len(df_cisd) < 10: return False, 0.0, 0.0
    last_candle = df_cisd.iloc[-1]
    swing_high = df_cisd['high'].iloc[-7:-2].max()
    swing_low = df_cisd['low'].iloc[-7:-2].min()
    
    if bias == "BULLISH" and last_candle['close'] > swing_high:
        return True, last_candle['close'], df_cisd['low'].iloc[-5:].min() * 0.9995
    elif bias == "BEARISH" and last_candle['close'] < swing_low:
        return True, last_candle['close'], df_cisd['high'].iloc[-5:].max() * 1.0005
    return False, 0.0, 0.0

def cek_fvg_atau_swing_poi(df):
    """Mengecek POI dan mengembalikan catatan penjelasannya"""
    if len(df) < 5: return False, "Tidak ada POI kuat (Middle Zone)"
    c1, c3 = df.iloc[-3], df.iloc[-1]
    
    fvg_bullish = c3['low'] > c1['high']
    fvg_bearish = c3['high'] < c1['low']
    
    lokal_low = df['low'].tail(20).min()
    lokal_high = df['high'].tail(20).max()
    dekat_swing_low = abs(c3['close'] - lokal_low) / lokal_low < 0.0015
    dekat_swing_high = abs(c3['close'] - lokal_high) / lokal_high < 0.0015
    
    if fvg_bullish or fvg_bearish:
        return True, "Valid Fair Value Gap (FVG Zone)"
    if dekat_swing_low or dekat_swing_high:
        return True, "Retest Ekstrem Swing High/Low (ERL)"
        
    return False, "Tidak ada POI kuat (Middle Zone)"

def jalankan_bot():
    print("🚀 Memulai Scanning dengan Penjelasan Analisa Terperinci...")
    for market in WATCHLIST:
        for setup in STRUKTUR_SETUP:
            df_bias = get_binance_data(market, interval=setup["bias_tf"])
            df_crt = get_binance_data(market, interval=setup["crt_tf"])
            
            if df_bias.empty or df_crt.empty: continue
                
            bias_utama, alasan_bias = hitung_bias_htf(df_bias)
            if bias_utama == "NEUTRAL": continue
                
            candle_swept = df_crt.iloc[-1]
            candle_acuan = df_crt.iloc[-2]
            
            crt_valid = False
            if bias_utama == "BULLISH":
                if candle_swept['low'] < candle_acuan['low'] and candle_swept['close'] > candle_acuan['low']:
                    crt_valid = True
            elif bias_utama == "BEARISH":
                if candle_swept['high'] > candle_acuan['high'] and candle_swept['close'] < candle_acuan['high']:
                    crt_valid = True
                    
            if crt_valid:
                df_cisd = get_binance_data(market, interval=setup["cisd_tf"], limit=50)
                cisd_confirmed, entry_price, sl_price = cari_cisd_mikro(df_cisd, bias_utama)
                
                if cisd_confirmed:
                    # Ambil Alasan Kualitas POI
                    is_high_prob, alasan_poi = cek_fvg_atau_swing_poi(df_crt)
                    status_prob = "🔥 HIGH PROBABILITY" if is_high_prob else "⚠️ LOW PROBABILITY"
                    
                    if bias_utama == "BULLISH":
                        risk = entry_price - sl_price
                        tp_price = entry_price + (risk * 2)
                    else:
                        risk = sl_price - entry_price
                        tp_price = entry_price - (risk * 2)
                        
                    desimal = 4 if entry_price < 10 else (2 if entry_price < 1000 else 1)
                    
                    # FORMAT PESAN DENGAN MATRIKS PENJELASAN (DIREVISI)
                    pesan = (
                        f"⚡ *FRAKTAL CRT SIGNAL DETECTED* ⚡\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *Asset:* #{market}\n"
                        f"📐 *Model:* {setup['nama']}\n"
                        f"📈 *{setup['bias_tf'].upper()} Bias:* {bias_utama}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📖 *PENJELASAN ANALISA (MARKET CONTEXT):*\n"
                        f"• *Pemicu Bias:* {alasan_bias}\n"
                        f"• *Trigger CRT:* Valid Swept Candle pada TF {setup['crt_tf'].upper()}\n"
                        f"• *Area Kedudukan:* {alasan_poi} ({status_prob})\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎯 *PRESET ORDER DATA (SET & FORGET):*\n\n"
                        f"🟢 *ENTRY PRICE :* `{entry_price:.{desimal}f}`\n"
                        f"🔴 *STOP LOSS (SL):* `{sl_price:.{desimal}f}` *(Swing {setup['cisd_tf'].upper()})*\n"
                        f"🔵 *TAKE PROFIT (TP):* `{tp_price:.{desimal}f}` *(RR 1:2 Min)*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💡 *Info:* Konfirmasi patah struktur (CISD) di TF {setup['cisd_tf'].upper()} sah. Silakan pasang order.\n"
                        f"⏰ *Waktu Server:* {datetime.datetime.utcnow().strftime('%H:%M')} UTC"
                    )
                    kirim_notifikasi_telegram(pesan)
                    
    print("✅ Scanning selesai.")

if __name__ == "__main__":
    jalankan_bot()