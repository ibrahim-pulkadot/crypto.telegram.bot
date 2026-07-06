"""OpenAI uyumlu bir LLM API'si üzerinden görsel + indikatör analizi yapar."""
import base64
import json
import time

import requests

import config

# Ana model başarısız olursa denenecek yedekler; .env'deki LLM_FALLBACK_MODELS'ten gelir.
FALLBACK_MODELS = config.LLM_FALLBACK_MODELS
MAX_RETRIES = 3

SYSTEM_PROMPT = (
    "Sen deneyimli bir teknik analiz uzmanısın. Sana bir kripto paranın çoklu zaman "
    "aralığındaki teknik indikatör değerleri ve (varsa) grafik görseli verilecek. "
    "Bu verileri birlikte değerlendirip olasılıksal bir senaryo çıkaracaksın.\n"
    "Kurallar:\n"
    "- Sadece verilen verilere dayan, veri uydurma.\n"
    "- Görsel varsa formasyon, trend çizgileri ve mum yapısını da yorumla.\n"
    "- 'confidence' değerini indikatörlerin ne kadar hemfikir olduğuna göre belirt.\n"
    "- Bu bir yatırım tavsiyesi DEĞİLDİR; çıktı olasılıksaldır.\n"
    "- Yanıtı YALNIZCA aşağıdaki JSON şemasında ver, ekstra metin yazma."
)

JSON_SCHEMA_HINT = {
    "direction": "yükseliş | düşüş | nötr",
    "confidence": "0-100 arası tam sayı",
    "timeframe_bias": "kısa vade ve orta vade yön özeti (kısa metin)",
    "reasoning": "2-4 cümle, indikatörlere dayalı gerekçe (Türkçe)",
    "key_levels": {"support": ["sayı"], "resistance": ["sayı"]},
    "entry_zone": "giriş bölgesi aralığı (metin)",
    "stop_loss": "stop-loss seviyesi (metin veya sayı)",
    "take_profit": ["hedef seviyeler"],
    "invalidation": "senaryonun geçersiz olacağı koşul (kısa metin)",
    "risk_note": "kısa risk uyarısı (Türkçe)",
}


def _build_user_content(indicator_summary: dict, image_bytes: bytes | None) -> list:
    text = (
        f"Sembol: {indicator_summary.get('symbol')}\n\n"
        f"Teknik indikatör özeti (zaman aralığı bazında):\n"
        f"{json.dumps(indicator_summary.get('timeframes', {}), ensure_ascii=False, indent=2)}\n\n"
        f"Lütfen analizini YALNIZCA şu JSON şemasıyla döndür:\n"
        f"{json.dumps(JSON_SCHEMA_HINT, ensure_ascii=False, indent=2)}"
    )
    content = [{"type": "text", "text": text}]
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        )
    return content


def _call_model(model: str, content: list) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{config.LLM_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return _parse_json(data["choices"][0]["message"]["content"])


def analyze(indicator_summary: dict, image_bytes: bytes | None = None) -> dict:
    """Model analizi yapar; geçici hatalarda retry ve yedek modele geçer."""
    content = _build_user_content(indicator_summary, image_bytes)
    models = [config.LLM_MODEL] + [m for m in FALLBACK_MODELS if m != config.LLM_MODEL]

    last_err = None
    for model in models:
        for attempt in range(MAX_RETRIES):
            try:
                return _call_model(model, content)
            except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                # 401/400 kalıcı hatadır; retry etme, sıradaki modele de geçme
                if status in (401, 403):
                    raise
                time.sleep(1.5 * (attempt + 1))
            except (json.JSONDecodeError, KeyError) as e:
                last_err = e
                time.sleep(1.0)
    raise RuntimeError(f"Analiz tüm modellerde başarısız oldu: {last_err}")


def _parse_json(content: str) -> dict:
    """Model çıktısını JSON'a çevirir; markdown çiti varsa temizler."""
    content = content.strip()
    if content.startswith("```"):
        # ```json ... ``` bloklarını temizle
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # İlk { ile son } arasını dene
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start : end + 1])
        raise
