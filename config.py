"""Ortam değişkenlerinden yapılandırma yükler."""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")

# OpenAI uyumlu LLM sağlayıcısı — tüm adres/anahtar/model .env'den okunur.
LLM_API_KEY = _get("LLM_API_KEY")
LLM_BASE_URL = _get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = _get("LLM_MODEL", "gpt-4o-mini")
LLM_FALLBACK_MODELS = [m.strip() for m in _get("LLM_FALLBACK_MODELS").split(",") if m.strip()]

EXCHANGE_ID = _get("EXCHANGE_ID", "binance")
TIMEFRAMES = [t.strip() for t in _get("TIMEFRAMES", "1h,4h,1d").split(",") if t.strip()]
CANDLE_LIMIT = int(_get("CANDLE_LIMIT", "200"))
RATE_LIMIT_PER_MIN = int(_get("RATE_LIMIT_PER_MIN", "5"))

# Analiz motorunun bakacağı ana zaman aralığı (indikatör seviyeleri için)
PRIMARY_TIMEFRAME = TIMEFRAMES[1] if len(TIMEFRAMES) > 1 else TIMEFRAMES[0]


def validate() -> list[str]:
    """Eksik/yanlış ayarları döndürür (boş liste = her şey tamam)."""
    problems = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("buraya"):
        problems.append("TELEGRAM_BOT_TOKEN ayarlı değil (.env)")
    if not LLM_API_KEY or not LLM_API_KEY.startswith("sk-"):
        problems.append("LLM_API_KEY ayarlı değil (.env)")
    return problems
