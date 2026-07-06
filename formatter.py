"""Analiz JSON'unu okunabilir Telegram mesajına çevirir."""

_ARROW = {"yükseliş": "🟢", "düşüş": "🔴", "nötr": "⚪"}


def _fmt_levels(levels) -> str:
    if not levels:
        return "-"
    if isinstance(levels, list):
        return " / ".join(str(x) for x in levels)
    return str(levels)


def format_analysis(symbol: str, primary_tf: str, result: dict) -> str:
    direction = str(result.get("direction", "nötr")).lower()
    icon = _ARROW.get(direction, "⚪")
    confidence = result.get("confidence", "?")

    key = result.get("key_levels", {}) or {}
    support = _fmt_levels(key.get("support"))
    resistance = _fmt_levels(key.get("resistance"))

    lines = [
        f"📊 *{symbol}* — Analiz ({primary_tf})",
        "",
        f"{icon} *Yön:* {direction.upper()}  |  *Güven:* %{confidence}",
    ]

    if result.get("timeframe_bias"):
        lines.append(f"🕒 {result['timeframe_bias']}")

    lines.append("")
    if result.get("reasoning"):
        lines.append(f"📌 *Gerekçe:* {result['reasoning']}")
        lines.append("")

    lines.append(f"🎯 *Destek:* {support}")
    lines.append(f"🎯 *Direnç:* {resistance}")

    if result.get("entry_zone"):
        lines.append(f"📥 *Giriş bölgesi:* {result['entry_zone']}")
    if result.get("stop_loss"):
        lines.append(f"🛑 *Stop-loss:* {result['stop_loss']}")
    if result.get("take_profit"):
        lines.append(f"🏁 *Hedefler:* {_fmt_levels(result['take_profit'])}")
    if result.get("invalidation"):
        lines.append(f"❌ *Geçersizlik:* {result['invalidation']}")

    lines.append("")
    risk = result.get("risk_note") or (
        "Yatırım tavsiyesi değildir. Olasılıksal senaryodur; kendi araştırmanızı yapın."
    )
    lines.append(f"⚠️ _{risk}_")

    return "\n".join(lines)


_CLASS_TR = {"up": "yükseliş", "down": "düşüş", "neutral": "nötr"}
_CLASS_ICON = {"up": "🟢", "down": "🔴", "neutral": "⚪"}


def format_backtest(result: dict) -> str:
    from datetime import datetime, timezone

    acc = result["accuracy"]
    dir_acc = result.get("directional_accuracy")
    icon = "🟢" if acc >= 60 else ("🟡" if acc >= 40 else "🔴")

    lines = [
        f"🎯 *Doğruluk Analizi* — {result['symbol']} ({result['timeframe']})",
        "",
        f"{icon} *Genel isabet:* %{acc}  ({result['correct']}/{result['points_tested']})",
    ]
    if dir_acc is not None:
        lines.append(f"↕️ *Yönlü isabet:* %{dir_acc}  (nötr tahminler hariç)")
    lines.append(
        f"⚙️ Test: {result['points_tested']} geçmiş nokta, {result['horizon']} mum "
        f"ileriye bakıldı, eşik ±%{result['threshold']}"
    )
    lines.append("")

    for c in result["checks"]:
        if "error" in c:
            lines.append("• ⚠️ (bir noktada analiz hatası)")
            continue
        try:
            t = datetime.fromtimestamp(c["time"] / 1000, tz=timezone.utc).strftime("%d.%m %H:%M")
        except Exception:
            t = "?"
        mark = "✅" if c["correct"] else "❌"
        pi = _CLASS_ICON.get(c["pred_class"], "⚪")
        ri = _CLASS_ICON.get(c["realized_class"], "⚪")
        lines.append(
            f"{mark} {t} | tahmin {pi}{_CLASS_TR.get(c['pred_class'])} → "
            f"gerçek {ri}{_CLASS_TR.get(c['realized_class'])} ({c['ret_pct']:+}%)"
        )

    lines.append("")
    lines.append(
        "⚠️ _Geçmiş performans gelecek için garanti değildir. Sınırlı sayıda "
        "noktada yapılan bu test istatistiksel kesinlik taşımaz._"
    )
    return "\n".join(lines)


def escape_markdown(text: str) -> str:
    """Telegram legacy Markdown için minimal kaçış (mesaj gövdesi için)."""
    return text
