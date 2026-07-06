"""Teknik indikatörler — saf Python (pandas/numpy/ta KULLANMAZ)."""
from __future__ import annotations


def _round(v, n=6):
    if v is None:
        return None
    return round(v, n)


def ema_series(vals: list[float], period: int) -> list[float]:
    """Basit özyinelemeli EMA serisi (ilk değerle tohumlanır)."""
    if not vals:
        return []
    k = 2 / (period + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema_last(vals: list[float], period: int):
    if len(vals) < period:
        return None
    return ema_series(vals, period)[-1]


def sma(vals: list[float], period: int):
    if len(vals) < period:
        return None
    return sum(vals[-period:]) / period


def rsi(closes: list[float], period: int = 14):
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g = ch if ch > 0 else 0.0
        l = -ch if ch < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(closes: list[float], fast=12, slow=26, signal=9):
    """(macd_line_last, signal_last, hist_last) döndürür."""
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema_series(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], hist


def bollinger(closes: list[float], period=20, dev=2):
    if len(closes) < period:
        return None, None
    window = closes[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    std = var ** 0.5
    return mean + dev * std, mean - dev * std


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    a = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        a = (a * (period - 1) + trs[i]) / period
    return a


def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < 2 * period + 1:
        return None
    plus_dm, minus_dm, tr = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    def wilder(vals):
        s = sum(vals[:period])
        out = [s]
        for i in range(period, len(vals)):
            s = s - s / period + vals[i]
            out.append(s)
        return out

    tr_s, pdm_s, mdm_s = wilder(tr), wilder(plus_dm), wilder(minus_dm)
    dx = []
    for i in range(len(tr_s)):
        if tr_s[i] == 0:
            dx.append(0.0)
            continue
        pdi = 100 * pdm_s[i] / tr_s[i]
        mdi = 100 * mdm_s[i] / tr_s[i]
        denom = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / denom if denom else 0.0)
    if len(dx) < period:
        return None
    a = sum(dx[:period]) / period
    for i in range(period, len(dx)):
        a = (a * (period - 1) + dx[i]) / period
    return a


def stochastic(highs, lows, closes, period=14):
    if len(closes) < period:
        return None
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return 50.0
    return 100 * (closes[-1] - ll) / (hh - ll)


def compute(o: dict) -> dict:
    """Bir zaman aralığı için indikatör özeti (o = data.fetch_ohlcv çıktısı)."""
    close = o["close"]
    high = o["high"]
    low = o["low"]
    volume = o["volume"]
    last = close[-1]

    macd_line, macd_sig, macd_hist = macd(close)
    bb_high, bb_low = bollinger(close)

    look = min(50, len(close))
    support = min(low[-look:])
    resistance = max(high[-look:])

    vol_avg = sma(volume, min(20, len(volume)))
    change_50 = ((last / close[-50] - 1) * 100) if len(close) >= 50 else None

    return {
        "price": _round(last),
        "ema20": _round(ema_last(close, 20)),
        "ema50": _round(ema_last(close, 50)),
        "ema200": _round(ema_last(close, 200)),
        "rsi": _round(rsi(close), 2),
        "macd": _round(macd_line),
        "macd_signal": _round(macd_sig),
        "macd_hist": _round(macd_hist),
        "bb_high": _round(bb_high),
        "bb_low": _round(bb_low),
        "atr": _round(atr(high, low, close)),
        "adx": _round(adx(high, low, close), 2),
        "stoch": _round(stochastic(high, low, close), 2),
        "support": _round(support),
        "resistance": _round(resistance),
        "volume_last": _round(volume[-1], 2),
        "volume_avg20": _round(vol_avg, 2),
        "price_change_pct_50": _round(change_50, 2),
    }


def multi_timeframe_summary(symbol: str, ohlcv_by_tf: dict) -> dict:
    out = {}
    for tf, o in ohlcv_by_tf.items():
        if o is None or len(o["close"]) < 30:
            continue
        out[tf] = compute(o)
    return {"symbol": symbol, "timeframes": out}
