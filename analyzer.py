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
    "Sen kıdemli bir kripto teknik analiz uzmanısın. Sana bir kripto paranın çoklu zaman "
    "aralığındaki teknik indikatör değerleri ve (varsa) bir grafik görseli verilecek. "
    "Amacın rastgele yön atmak değil; indikatörler arasındaki UYUMA (confluence) dayalı, "
    "temkinli ve kalibre edilmiş bir olasılıksal senaryo üretmek.\n\n"
    "Analiz yöntemi (bu sırayla düşün, ama yalnızca sonucu JSON olarak ver):\n"
    "1. Trend yönü: EMA20/EMA50/EMA200 sıralaması ve fiyatın konumu. EMA20>EMA50>EMA200 ve "
    "fiyat üstündeyse güçlü yükseliş; ters sıralama güçlü düşüş; karışıksa yatay/belirsiz.\n"
    "2. Trend gücü: ADX>25 güçlü trend (yön EMA'lara göre), ADX<20 zayıf/yatay trend — bu "
    "durumda yönlü iddiadan kaçın, 'nötr'e yaklaş.\n"
    "3. Momentum: RSI (>70 aşırı alım, <30 aşırı satım, 45-55 nötr), MACD'nin sinyal "
    "çizgisine göre konumu ve histogram yönü, Stochastic aşırı bölgeleri. Bunlar trendle AYNI "
    "yönde mi? (uyum = güven artışı, çelişki = güven azalışı).\n"
    "4. Volatilite/konum: Bollinger bantlarına göre fiyatın konumu; ATR ile mevcut oynaklığı "
    "stop-loss ve hedef mesafelerini ölçeklendirmek için kullan.\n"
    "5. Hacim: volume_last / volume_avg20 oranı — hareketi hacim destekliyor mu (>1 destekli, "
    "<0.7 zayıf/şüpheli).\n"
    "6. Zaman aralıkları çelişiyorsa (ör. 1h yükseliş, 1d düşüş) bunu timeframe_bias'ta açıkça "
    "belirt; genel yönü daha uzun vadeli aralığa (1d > 4h > 1h) ağırlık vererek belirle. "
    "Çelişki büyükse direction'ı 'nötr' yap.\n\n"
    "Confidence kalibrasyonu (0-100): trend, trend gücü, momentum, hacim, TF-uyumu olmak "
    "üzere 5 kategoriden kaçı aynı yönü destekliyorsa confidence ona göre artsın — hepsi "
    "çelişkiliyse 30'un altında kal, hepsi uyumluysa 70+ olabilir. Tek bir indikatöre dayanıp "
    "yüksek confidence VERME.\n\n"
    "Kurallar:\n"
    "- Sadece verilen verilere dayan, veri uydurma; verilmeyen bir zaman aralığından bahsetme.\n"
    "- Görsel varsa formasyon, trend çizgileri ve mum yapısını da yorumla; sayısal verilerle "
    "çelişirse sayısal veriye öncelik ver.\n"
    "- Kullanıcının özel bir isteği varsa onu da dikkate al.\n"
    "- Belirsizlik/çelişki durumunda dürüstçe 'nötr' de ve confidence'ı düşük tut — yanlış "
    "kesinlik gösterme.\n"
    "- Güncel haber başlıkları verilirse bunları ek bağlam olarak değerlendir; ancak "
    "teknik veriyle çelişen spekülatif/duygusal başlıklara aşırı ağırlık verme — teknik "
    "veri her zaman önceliklidir. Haberlerin analizi nasıl etkilediğini 'news_impact' "
    "alanında tek cümleyle özetle (haber verilmediyse alanı boş bırak).\n"
    "- Bu bir yatırım tavsiyesi DEĞİLDİR; çıktı olasılıksaldır.\n"
    "- Yanıtı YALNIZCA aşağıdaki JSON şemasında ver, ekstra metin yazma."
)

CHAT_SYSTEM_PROMPT = (
    "Sen deneyimli, samimi bir kripto teknik analiz asistanısın. Kullanıcı sana "
    "serbest bir dille yazar (ör. '3 aylık veriye bak ve tahmin yap', 'günlük trend "
    "nasıl?'). Sana ilgili kripto paranın GERÇEK indikatör verileri verilir.\n"
    "Tahmin/yön istendiğinde şu confluence yöntemini uygula: (1) EMA20/50/200 sıralaması "
    "ile trend yönü, (2) ADX ile trend gücü (ADX<20 ise yatay/belirsiz de), (3) RSI/MACD/"
    "Stochastic'in trendle uyumu, (4) Bollinger/ATR ile volatilite ve seviye mesafeleri, "
    "(5) hacmin (volume_last vs volume_avg20) hareketi destekleyip desteklemediği. Bu "
    "kategoriler ne kadar aynı yönü gösteriyorsa o kadar kararlı konuş; çelişkiliyse bunu "
    "açıkça söyle ve aşırı kesin ifadelerden kaçın.\n"
    "Güncel haber başlıkları verilirse ek bağlam olarak değerlendir; teknik veriyle çelişen "
    "spekülatif/duygusal başlıklara aşırı ağırlık verme, teknik veri her zaman önceliklidir.\n"
    "Kurallar:\n"
    "- Kullanıcının tam olarak istediği şeyi yap; gereksiz genel geçer laf etme.\n"
    "- Sadece verilen gerçek verilere dayan, fiyat/veri UYDURMA.\n"
    "- Anlaşılır Türkçe yaz; uygun yerlerde madde imleri, net seviyeler ve olasılık ver.\n"
    "- Tahmin istenirse yön, olası senaryolar, önemli destek/direnç ve geçersizlik koşulu ver.\n"
    "- Cevabın en sonuna tek satır '⚠️ Yatırım tavsiyesi değildir.' notu ekle.\n"
    "- Telegram için sade Markdown kullan: kalın için tek *yıldız* (ör. *Trend Yönü*), "
    "liste maddeleri için '-' kullan; '*' KARAKTERİNİ ASLA liste imi olarak kullanma "
    "(kalın işaretiyle karışır ve mesaj bozulur). Kalın içinde başka biçimlendirme iç içe "
    "geçirme, biçimi abartma."
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
    "news_impact": "haberlerin analize etkisi, tek cümle (haber yoksa boş bırak)",
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
                        user_request: str | None = None,
                        news_text: str | None = None) -> list:
    text = (
        f"Sembol: {indicator_summary.get('symbol')}\n\n"
        f"Teknik indikatör özeti (zaman aralığı bazında):\n"
        f"{json.dumps(indicator_summary.get('timeframes', {}), ensure_ascii=False, indent=2)}\n\n"
    )
    if news_text:
        text += (
            f"Güncel haber başlıkları (doğruluğu garanti edilmez, ek bağlam olarak kullan):\n"
            f"{news_text}\n\n"
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
            user_request: str | None = None, news_text: str | None = None) -> dict:
    """Şemalı (JSON) teknik analiz döndürür."""
    messages = [
        {"role": "system", "content": _system(SYSTEM_PROMPT)},
        {"role": "user", "content": _build_user_content(
            indicator_summary, image_bytes, user_request, news_text
        )},
    ]
    raw = _complete(messages, response_format={"type": "json_object"})
    return _parse_json(raw)


def chat_analyze(user_request: str, indicator_summary: dict,
                 image_bytes: bytes | None = None, news_text: str | None = None) -> str:
    """Kullanıcının serbest metin isteğine gerçek veriye dayalı serbest yanıt üretir."""
    text = (
        f"Kullanıcının isteği: {user_request}\n\n"
        f"Sembol: {indicator_summary.get('symbol')}\n"
        f"Gerçek teknik indikatör verileri (zaman aralığı bazında):\n"
        f"{json.dumps(indicator_summary.get('timeframes', {}), ensure_ascii=False, indent=2)}\n\n"
    )
    if news_text:
        text += (
            f"Güncel haber başlıkları (doğruluğu garanti edilmez, ek bağlam olarak kullan):\n"
            f"{news_text}\n\n"
        )
    text += "Bu gerçek verilere dayanarak kullanıcının isteğini eksiksiz yerine getir."
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
