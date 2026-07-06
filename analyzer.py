"""OpenAI uyumlu bir LLM API'si üzerinden analiz ve sohbet yapar."""
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
    "- Kullanıcının özel bir isteği varsa onu da dikkate al.\n"
    "- 'confidence' değerini indikatörlerin ne kadar hemfikir olduğuna göre belirt.\n"
    "- Bu bir yatırım tavsiyesi DEĞİLDİR; çıktı olasılıksaldır.\n"
    "- Yanıtı YALNIZCA aşağıdaki JSON şemasında ver, ekstra metin yazma."
)

CHAT_SYSTEM_PROMPT = (
    "Sen deneyimli, samimi bir kripto teknik analiz asistanısın. Kullanıcı sana "
    "serbest bir dille yazar (ör. '3 aylık veriye bak ve tahmin yap', 'günlük trend "
    "nasıl?'). Sana ilgili kripto paranın GERÇEK indikatör verileri verilir.\n"
    "Kurallar:\n"
    "- Kullanıcının tam olarak istediği şeyi yap; gereksiz genel geçer laf etme.\n"
    "- Sadece verilen gerçek verilere dayan, fiyat/veri UYDURMA.\n"
    "- Anlaşılır Türkçe yaz; uygun yerlerde madde imleri, net seviyeler ve olasılık ver.\n"
    "- Tahmin istenirse yön, olası senaryolar, önemli destek/direnç ve geçersizlik koşulu ver.\n"
    "- Cevabın en sonuna tek satır '⚠️ Yatırım tavsiyesi değildir.' notu ekle.\n"
    "- Telegram için sade Markdown kullan (kalın için tek *yıldız*); biçimi abartma."
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


def _system(base: str) -> str:
    """Sistem promptuna .env'deki bot kişiliğini (varsa) ekler."""
    if config.BOT_PERSONA:
        return f"{base}\n\nKİMLİK/TON: Adın '{config.BOT_NAME}'. {config.BOT_PERSONA}"
    return base


def _image_part(image_bytes: bytes) -> dict:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def _call(model: str, messages: list, response_format, temperature: float,
          max_tokens: int) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
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
    return resp.json()["choices"][0]["message"]["content"]


def _complete(messages: list, response_format=None, temperature: float = 0.4,
              max_tokens: int = 1200) -> str:
    """Modeli çağırır; geçici hatalarda retry, kalıcı hatada yedek modele geçer."""
    models = [config.LLM_MODEL] + [m for m in FALLBACK_MODELS if m != config.LLM_MODEL]
    last_err = None
    for model in models:
        for attempt in range(MAX_RETRIES):
            try:
                return _call(model, messages, response_format, temperature, max_tokens)
            except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                # 401/403 kalıcı hatadır; retry etme, sıradaki modele de geçme
                if status in (401, 403):
                    raise
                time.sleep(1.5 * (attempt + 1))
            except (KeyError, ValueError) as e:  # beklenmedik yanıt gövdesi
                last_err = e
                time.sleep(1.0)
    raise RuntimeError(f"LLM isteği tüm modellerde başarısız oldu: {last_err}")


def _build_user_content(indicator_summary: dict, image_bytes: bytes | None,
                        user_request: str | None = None) -> list:
    text = (
        f"Sembol: {indicator_summary.get('symbol')}\n\n"
        f"Teknik indikatör özeti (zaman aralığı bazında):\n"
        f"{json.dumps(indicator_summary.get('timeframes', {}), ensure_ascii=False, indent=2)}\n\n"
    )
    if user_request:
        text += f"Kullanıcının özel isteği: {user_request}\n\n"
    text += (
        f"Lütfen analizini YALNIZCA şu JSON şemasıyla döndür:\n"
        f"{json.dumps(JSON_SCHEMA_HINT, ensure_ascii=False, indent=2)}"
    )
    content = [{"type": "text", "text": text}]
    if image_bytes:
        content.append(_image_part(image_bytes))
    return content


def analyze(indicator_summary: dict, image_bytes: bytes | None = None,
            user_request: str | None = None) -> dict:
    """Şemalı (JSON) teknik analiz döndürür."""
    messages = [
        {"role": "system", "content": _system(SYSTEM_PROMPT)},
        {"role": "user", "content": _build_user_content(indicator_summary, image_bytes, user_request)},
    ]
    raw = _complete(messages, response_format={"type": "json_object"})
    return _parse_json(raw)


def chat_analyze(user_request: str, indicator_summary: dict,
                 image_bytes: bytes | None = None) -> str:
    """Kullanıcının serbest metin isteğine gerçek veriye dayalı serbest yanıt üretir."""
    text = (
        f"Kullanıcının isteği: {user_request}\n\n"
        f"Sembol: {indicator_summary.get('symbol')}\n"
        f"Gerçek teknik indikatör verileri (zaman aralığı bazında):\n"
        f"{json.dumps(indicator_summary.get('timeframes', {}), ensure_ascii=False, indent=2)}\n\n"
        "Bu gerçek verilere dayanarak kullanıcının isteğini eksiksiz yerine getir."
    )
    content = [{"type": "text", "text": text}]
    if image_bytes:
        content.append(_image_part(image_bytes))
    messages = [
        {"role": "system", "content": _system(CHAT_SYSTEM_PROMPT)},
        {"role": "user", "content": content},
    ]
    return _complete(messages, temperature=0.5, max_tokens=1500).strip()


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
