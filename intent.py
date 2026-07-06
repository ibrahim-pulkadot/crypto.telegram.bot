"""Serbest metin isteğini (sohbet) yapısal analiz parametrelerine çevirir — LLM ile."""
import analyzer

# ccxt'nin yaygın desteklediği mum aralıkları
_TF_ALLOWED = {
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w",
}

_SYSTEM = (
    "Kullanıcının kripto ile ilgili serbest metin mesajını yapısal parametrelere çevir. "
    "SADECE geçerli JSON döndür, başka metin yazma. Şema:\n"
    '{"symbol": "coin sembolü (ör. BTC, ETH) ya da null", '
    '"timeframe": "mum aralığı: 1h/4h/1d/1w gibi", '
    '"candle_limit": "çekilecek mum sayısı (tam sayı)", '
    '"request": "kullanıcının ne istediği, kısa ve Türkçe", '
    '"is_analysis": "kullanıcı bir coin analizi/tahmini/yorumu mu istiyor? true/false"}\n'
    "Kurallar:\n"
    "- Mesajda coin geçmiyorsa symbol=null.\n"
    "- Kullanıcı bir süre belirttiyse buna uygun timeframe + candle_limit seç. Örnekler: "
    "'3 aylık' → timeframe '1d', candle_limit 90. '1 yıllık' → '1d', 365. "
    "'son 1 hafta' → '1h', 168. 'son 24 saat' → '15m', 96. 'günlük' → '1d', 200. "
    "'saatlik' → '1h', 200. Süre belirtilmediyse → '4h', 200.\n"
    "- candle_limit en fazla 1000, en az 30 olsun."
)


def parse(text: str) -> dict:
    """Serbest metni {symbol, timeframe, candle_limit, request, is_analysis} yapar."""
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": text},
    ]
    raw = analyzer._complete(
        messages, response_format={"type": "json_object"},
        temperature=0.1, max_tokens=300,
    )
    data = analyzer._parse_json(raw)

    tf = str(data.get("timeframe") or "4h").lower().strip()
    if tf not in _TF_ALLOWED:
        tf = "4h"

    try:
        limit = int(data.get("candle_limit") or 200)
    except (ValueError, TypeError):
        limit = 200
    limit = max(30, min(1000, limit))

    symbol = data.get("symbol")
    if isinstance(symbol, str):
        symbol = symbol.strip() or None

    return {
        "symbol": symbol,
        "timeframe": tf,
        "candle_limit": limit,
        "request": (data.get("request") or text).strip(),
        "is_analysis": bool(data.get("is_analysis", True)),
    }
