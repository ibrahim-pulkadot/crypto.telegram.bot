"""Telegram olmadan çekirdek analiz zincirini test eder."""
import sys
import data
import indicators
import analyzer
import formatter
import config

symbol_raw = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
symbol = data.normalize_symbol(symbol_raw)
print(f"[1] Sembol: {symbol}  Borsa: {config.EXCHANGE_ID}  TF: {config.TIMEFRAMES}")

ohlcv = {}
for tf in config.TIMEFRAMES:
    try:
        o = data.fetch_ohlcv(symbol, tf, config.CANDLE_LIMIT)
        ohlcv[tf] = o
        print(f"[2] {tf}: {len(o['close'])} mum, son fiyat={o['close'][-1]}")
    except Exception as e:
        print(f"[2] {tf}: HATA {type(e).__name__}: {e}")

if not ohlcv:
    print("Veri alınamadı, çıkılıyor.")
    sys.exit(1)

summary = indicators.multi_timeframe_summary(symbol, ohlcv)
print("[3] İndikatör özeti hazır. Örnek (primary tf):")
import json
print(json.dumps(summary["timeframes"].get(config.PRIMARY_TIMEFRAME, {}), ensure_ascii=False, indent=2))

print("[4] AI analizi çağrılıyor...")
result = analyzer.analyze(summary, image_bytes=None)
print("[4] Ham sonuç:")
print(json.dumps(result, ensure_ascii=False, indent=2))

msg = formatter.format_analysis(symbol, config.PRIMARY_TIMEFRAME, result)
with open("last_message.txt", "w", encoding="utf-8") as f:
    f.write(msg)
print("\n[5] Telegram mesajı last_message.txt dosyasına yazıldı.")
