"""Doğruluk analizi (backtest): geçmiş noktalarda AI tahmini yaptırıp
sonrasında fiyatın gerçekte ne yaptığını karşılaştırır ve isabet oranı verir."""
from __future__ import annotations

import data
import indicators
import analyzer


def _dir_class(direction: str) -> str:
    d = (direction or "").lower()
    if "yüksel" in d or "yuksel" in d or "up" in d or "bull" in d:
        return "up"
    if "düş" in d or "dus" in d or "down" in d or "bear" in d:
        return "down"
    return "neutral"


def _realized_class(ret_pct: float, threshold: float) -> str:
    if ret_pct > threshold:
        return "up"
    if ret_pct < -threshold:
        return "down"
    return "neutral"


def _slice(o: dict, end_idx: int) -> dict:
    return {k: v[: end_idx + 1] for k, v in o.items()}


def run_backtest(symbol_raw: str, timeframe: str, points: int = 5,
                 horizon: int = 6, threshold: float = 0.5,
                 fetch_limit: int = 320) -> dict:
    """Belirli sembol/zaman aralığında `points` geçmiş noktada tahmin test eder.

    horizon: tahminin kaç mum sonrasına bakılacağı.
    threshold: yüzde eşiği (bu kadar hareket yoksa 'nötr' sayılır).
    """
    symbol = data.normalize_symbol(symbol_raw)
    o = data.fetch_ohlcv(symbol, timeframe, fetch_limit)
    n = len(o["close"])

    # İndikatörler için yeterli geçmiş + tahmin sonrası için horizon mum gerekli
    min_history = 210
    start = min_history
    end = n - horizon - 1
    if end <= start:
        # Yeterli veri yoksa geçmiş şartını gevşet
        start = min(120, n // 2)
        end = n - horizon - 1
    if end <= start:
        raise ValueError("Backtest için yeterli veri yok.")

    if points <= 1:
        positions = [end]
    else:
        step = (end - start) / (points - 1)
        positions = sorted({int(start + round(step * i)) for i in range(points)})

    checks = []
    correct = 0
    for idx in positions:
        sliced = _slice(o, idx)
        summary = indicators.multi_timeframe_summary(symbol, {timeframe: sliced})
        try:
            res = analyzer.analyze(summary)  # sadece veri (görsel yok)
        except Exception as e:
            checks.append({"idx": idx, "error": str(e)})
            continue

        pred = _dir_class(res.get("direction", ""))
        entry = o["close"][idx]
        future = o["close"][idx + horizon]
        ret_pct = (future / entry - 1) * 100
        realized = _realized_class(ret_pct, threshold)
        is_correct = pred == realized

        if is_correct:
            correct += 1
        checks.append({
            "time": o["ts"][idx],
            "entry": round(entry, 6),
            "future": round(future, 6),
            "pred": res.get("direction", ""),
            "pred_class": pred,
            "realized_class": realized,
            "ret_pct": round(ret_pct, 2),
            "confidence": res.get("confidence"),
            "correct": is_correct,
        })

    valid = [c for c in checks if "error" not in c]
    total = len(valid)
    accuracy = round(correct / total * 100, 1) if total else 0.0

    # Sadece yönlü (nötr olmayan) tahminlerde isabet
    directional = [c for c in valid if c["pred_class"] in ("up", "down")]
    dir_correct = sum(1 for c in directional if c["correct"])
    dir_accuracy = round(dir_correct / len(directional) * 100, 1) if directional else None

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon": horizon,
        "threshold": threshold,
        "points_tested": total,
        "correct": correct,
        "accuracy": accuracy,
        "directional_accuracy": dir_accuracy,
        "checks": checks,
    }
