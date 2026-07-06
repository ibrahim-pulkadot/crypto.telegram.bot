"""Borsadan (ccxt) OHLCV verisi çeker. Saf Python — pandas kullanmaz."""
import ccxt

import config

_exchange = None


def get_exchange():
    global _exchange
    if _exchange is None:
        klass = getattr(ccxt, config.EXCHANGE_ID)
        _exchange = klass({"enableRateLimit": True})
    return _exchange


def normalize_symbol(raw: str) -> str:
    """'btc', 'BTCUSDT', 'btc/usdt' gibi girdileri 'BTC/USDT' biçimine çevirir."""
    s = raw.strip().upper().replace("-", "/").replace(" ", "")
    if "/" in s:
        return s
    for quote in ("USDT", "USDC", "USD", "TRY", "BTC", "ETH", "EUR"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[:-len(quote)]}/{quote}"
    return f"{s}/USDT"


def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> dict:
    """OHLCV'yi sütun listelerine ayrılmış dict olarak döndürür.

    { 'ts': [...], 'open': [...], 'high': [...], 'low': [...],
      'close': [...], 'volume': [...] }
    """
    ex = get_exchange()
    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return {
        "ts": [r[0] for r in raw],
        "open": [float(r[1]) for r in raw],
        "high": [float(r[2]) for r in raw],
        "low": [float(r[3]) for r in raw],
        "close": [float(r[4]) for r in raw],
        "volume": [float(r[5]) for r in raw],
    }


def symbol_exists(symbol: str) -> bool:
    ex = get_exchange()
    try:
        ex.load_markets()
        return symbol in ex.markets
    except Exception:
        return False
