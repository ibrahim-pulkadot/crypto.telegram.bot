# crypto.telegram.bot — Telegram Kripto Analiz Botu

Bir coin gönder; borsadan **gerçek OHLCV verisi** çeker, teknik indikatörleri saf Python ile hesaplar ve **OpenAI uyumlu bir LLM** (vision destekli) ile olasılıksal bir teknik senaryo çıkarır. İstersen bir **grafik görseli** de gönder — modeli hem görseli hem gerçek veriyi birlikte yorumlar.

> ⚠️ **Bu bot yatırım tavsiyesi vermez.** Çıktı, geçmiş fiyat verisine dayalı olasılıksal bir teknik senaryodur; kesinlik iddiası taşımaz. Kendi araştırmanı yap.

---

## Ne yapar?

- **Gerçek veri** — `ccxt` ile borsadan çoklu zaman aralığında (`1h/4h/1d`) OHLCV çeker, hiçbir şey uydurmaz.
- **Saf Python indikatörler** — `RSI`, `MACD`, `EMA`, `Bollinger`, `ATR`, `ADX`, `Stochastic` ve otomatik **destek/direnç** seviyeleri. `pandas`/`ta` **kullanılmaz**.
- **AI yorumu** — indikatör özetini (ve varsa grafik görselini) OpenAI uyumlu bir LLM API'sine verir; yön, güven skoru, giriş bölgesi, stop-loss, hedefler ve geçersizlik koşulunu **JSON** olarak alır.
- **Görsel + veri birlikte** — bir mum grafiği fotoğrafı gönderirsen, `vision` destekli model formasyon ve trend çizgilerini de yorumlar.
- **Doğruluk testi** — `/dogruluk` komutu, AI tahminlerini geçmiş noktalarda çalıştırıp isabet oranını ölçer.
- **Rate-limit** — kullanıcı başına dakikalık istek sınırı (varsayılan `5`).

---

## Kurulum

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Bağımlılıklar: `python-telegram-bot`, `ccxt`, `requests`, `python-dotenv`.

> **Not:** İndikatörler bilinçli olarak **saf Python** yazıldı. Geliştirme makinesinde WDAC güvenlik politikası imzasız yerel DLL'leri (`numpy.random`, `pandas`, `Pillow`) engellediği için `pandas`/`ta` kullanılmıyor — bu, botu her ortamda ek derleme gerektirmeden çalıştırılabilir yapar.

---

## Yapılandırma (`.env`)

`.env.example` dosyasını `.env` olarak kopyala ve doldur:

```powershell
copy .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=buraya_telegram_token   # BotFather'dan alınır
LLM_API_KEY=sk-...                          # OpenAI uyumlu API anahtarı
LLM_BASE_URL=https://api.openai.com/v1      # OpenAI uyumlu API adresi
LLM_MODEL=gpt-4o-mini                       # kullanılacak model (vision destekli)
LLM_FALLBACK_MODELS=                        # ana model düşerse denenecek yedekler (virgülle)
EXCHANGE_ID=binance                         # ccxt borsa id: bybit, okx, kucoin...
TIMEFRAMES=1h,4h,1d                         # analiz edilecek zaman aralıkları
CANDLE_LIMIT=200                            # her aralık için çekilecek mum sayısı
RATE_LIMIT_PER_MIN=5                        # kullanıcı başına dakikalık istek limiti
```

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | — | [@BotFather](https://t.me/BotFather)'a `/newbot` yazıp alınan token (**zorunlu**) |
| `LLM_API_KEY` | — | OpenAI uyumlu API anahtarı, `sk-` ile başlar (**zorunlu**) |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI uyumlu API adresi (istediğin sağlayıcı) |
| `LLM_MODEL` | `gpt-4o-mini` | Ana model (vision destekli olmalı) |
| `LLM_FALLBACK_MODELS` | — | Ana model başarısız olursa denenecek yedek modeller (virgülle) |
| `EXCHANGE_ID` | `binance` | ccxt borsa id |
| `TIMEFRAMES` | `1h,4h,1d` | Analiz zaman aralıkları (virgülle) |
| `CANDLE_LIMIT` | `200` | Aralık başına mum sayısı |
| `RATE_LIMIT_PER_MIN` | `5` | Kullanıcı başına dakikalık limit |

Model başlangıçta `config.validate()` ile doğrulanır; token veya API anahtarı eksikse bot açılmaz.

### 🔒 Güvenlik

- `.env` dosyasını **asla** paylaşma veya commit etme; gerçek `TELEGRAM_BOT_TOKEN` ve `LLM_API_KEY` gizli kalmalı (`.gitignore` içinde olduğundan emin ol).
- Repoya yalnızca sahte değerler içeren `.env.example` girer.
- Token'ın sızdıysa BotFather'dan `/revoke` ile yenile.

---

## Çalıştırma

```powershell
.\venv\Scripts\python.exe bot.py
```

Bot açıldıktan sonra Telegram'da:

- `BTC` veya `BTC/USDT` yaz
- `/analiz ETH`
- Bir **grafik görseli** gönder, caption'a coin adını yaz (örn. `SOL/USDT`)
- `/dogruluk BTC 4h` — AI tahminlerinin geçmişteki isabet oranını ölç

Sembol serbest biçim kabul eder: `btc`, `BTCUSDT`, `btc/usdt` → hepsi `BTC/USDT`'ye normalleştirilir (quote verilmezse `USDT` varsayılır).

---

## Test (Telegram gerekmez)

Uçtan uca zinciri (veri → indikatör → AI → mesaj) Telegram olmadan çalıştır:

```powershell
.\venv\Scripts\python.exe test_pipeline.py BTC/USDT
```

Üretilen mesaj `last_message.txt` dosyasına yazılır. Backtest'i ayrıca `test_backtest.py` ile denersin.

---

## Dosya yapısı

```
crypto.telegram.bot/
├─ bot.py            # Telegram giriş noktası: komutlar, foto, rate-limit
├─ data.py           # ccxt OHLCV çekme + sembol normalleştirme
├─ indicators.py     # saf Python indikatörler (RSI, MACD, EMA, Bollinger, ATR, ADX, Stoch, S/R)
├─ analyzer.py       # OpenAI uyumlu LLM çağrısı: system prompt, retry + yedek model, JSON parse
├─ formatter.py      # JSON analiz → düzenli Telegram mesajı
├─ backtest.py       # geçmiş noktalarda tahmin doğruluğu (/dogruluk)
├─ config.py         # .env yükleme ve doğrulama
├─ test_pipeline.py  # Telegram'sız uçtan uca test
├─ test_backtest.py  # backtest testi
├─ .env.example      # yapılandırma şablonu
└─ requirements.txt  # bağımlılıklar
```

---

## Nasıl çalışıyor (kısaca)

Telegram'dan gelen coin adı `data.normalize_symbol` ile `BASE/QUOTE` biçimine çevrilir, ardından her zaman aralığı için `ccxt` üzerinden OHLCV çekilir. `indicators.multi_timeframe_summary` bu ham veriden tüm göstergeleri saf Python ile hesaplayıp kompakt bir özet çıkarır. Bu özet (ve varsa base64'e çevrilmiş grafik görseli) `analyzer.analyze` ile OpenAI uyumlu bir `chat/completions` isteği olarak gönderilir; `response_format: json_object` ile şemalı yanıt istenir. Geçici hatalarda 3 kez yeniden denenir ve gerekirse `FALLBACK_MODELS` sırasıyla denenir (401/403 gibi kalıcı hatalarda durulur). Dönen JSON `formatter.format_analysis` ile okunabilir bir Telegram mesajına dönüştürülür. Senkron `ccxt`/`requests` çağrıları `asyncio.to_thread` ile ayrı thread'de çalışır, böylece event loop bloklanmaz.
