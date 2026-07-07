"""Telegram kripto analiz botu — giriş noktası."""
import asyncio
import logging
import re
import time
from collections import defaultdict, deque

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
import data
import indicators
import analyzer
import formatter
import backtest
import intent
import news

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("cryptobot")

# Kullanıcı başına istek zaman damgaları (basit rate-limit)
_requests: dict[int, deque] = defaultdict(deque)

# Haber okuma açık/kapalı — çalışırken /haber komutuyla değiştirilebilir (global, tüm kullanıcılar için).
_news_enabled = config.NEWS_ENABLED_DEFAULT


def _fetch_news_text(symbol: str) -> str | None:
    """Haber okuma açıksa sembolle ilgili başlıkları getirir; kapalıysa veya hata olursa None döner."""
    if not _news_enabled:
        return None
    try:
        items = news.fetch_news(symbol, limit=config.NEWS_MAX_ITEMS)
    except Exception:
        log.exception("Haber çekilemedi")
        return None
    return news.format_news_for_prompt(items) or None


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    dq = _requests[user_id]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= config.RATE_LIMIT_PER_MIN:
        return True
    dq.append(now)
    return False


def _authorized(user_id: int) -> bool:
    """ALLOWED_USER_IDS boşsa herkese açık; doluysa yalnızca listedekiler."""
    return not config.ALLOWED_USER_IDS or user_id in config.ALLOWED_USER_IDS


async def _guard(update: Update) -> bool:
    """Kullanıcı yetkisizse bilgilendirir ve True döndürür (işlem durdurulmalı)."""
    uid = update.effective_user.id
    if not _authorized(uid):
        log.info("Yetkisiz erişim reddedildi: user_id=%s", uid)
        await update.message.reply_text(
            "⛔ Bu bot özeldir; kullanım izniniz yok.\n"
            f"(Senin Telegram id'in: `{uid}`)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True
    return False


def _looks_like_bare_symbol(text: str) -> bool:
    """Tek kelimelik, sembol gibi görünen girdi mi? (ör. BTC, BTCUSDT, BTC/USDT)"""
    parts = (text or "").strip().split()
    if len(parts) != 1:
        return False
    core = parts[0].replace("/", "").replace("-", "")
    return bool(core) and core.isalnum() and len(core) <= 12


def _sanitize_markdown(text: str) -> str:
    """LLM çıktısını Telegram'ın (legacy) Markdown'ıyla uyumlu hale getirir.

    '* ' liste imi, kalın için kullanılan '*kelime*' ile aynı karakteri paylaştığı için
    tek sayıda '*'/'_' kalırsa Telegram "can't parse entities" hatası verir ve mesaj düz
    metin olarak (yıldızlar görünür halde) gönderilir. Liste imlerini '-' yapıp eşleşmeyen
    kalın/italik işaretlerini kaldırarak bunu önler.
    """
    text = re.sub(r"(?m)^(\s*)\*(\s+)", r"\1-\2", text)
    for ch in ("*", "_"):
        if text.count(ch) % 2 != 0:
            text = text.replace(ch, "")
    return text


async def _safe_edit(status, text: str):
    """Önce Markdown ile dener; biçim hatası olursa düz metne düşer."""
    text = _sanitize_markdown(text)
    try:
        await status.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        try:
            await status.edit_text(text)
        except Exception:
            log.exception("Mesaj güncellenemedi")


WELCOME = (
    "👋 *{name}*\n\n"
    "Bir coin gönder ya da benimle *sohbet edercesine* konuş — isteğini anlayıp "
    "gerçek veriyle analiz ederim.\n\n"
    "*Kullanım:*\n"
    "• `BTC` veya `BTC/USDT` → hızlı teknik analiz kartı\n"
    "• _\"BTC'nin 3 aylık verisine bak ve tahmin yap\"_ gibi serbest cümle yaz\n"
    "• _\"ETH günlük trend nasıl, kısa vade ne bekliyorsun?\"_\n"
    "• `/analiz ETH` — klasik kart\n"
    "• Bir grafik görseli gönder (caption'a coin adını/isteğini yaz)\n"
    "• `/dogruluk BTC 4h` — AI tahminlerinin geçmişteki isabet oranını ölç\n"
    "• `/haber` — haber okuma açık mı kapalı mı göster; `/haber ac` / `/haber kapat` ile değiştir\n"
    "• `yardım` yaz veya `/yardim` — bu listeyi tekrar gör\n\n"
    "⚠️ _Yatırım tavsiyesi değildir._"
)

_HELP_WORDS = {
    "yardım", "yardim", "help", "menü", "menu", "komutlar",
    "/yardım", "/yardim", "/help", "/menu", "?",
}


def _is_help_text(text: str) -> bool:
    return (text or "").strip().lower() in _HELP_WORDS


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    await update.message.reply_text(
        WELCOME.format(name=config.BOT_NAME), parse_mode=ParseMode.MARKDOWN
    )


async def _handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE, symbol_raw: str,
                  image_bytes: bytes | None):
    user_id = update.effective_user.id
    if _rate_limited(user_id):
        await update.message.reply_text(
            f"⏳ Çok fazla istek. Dakikada {config.RATE_LIMIT_PER_MIN} sorgu sınırı var."
        )
        return

    if not symbol_raw:
        await update.message.reply_text(
            "Hangi coin? Örn: `BTC` veya `/analiz ETH`", parse_mode=ParseMode.MARKDOWN
        )
        return

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    status = await update.message.reply_text("🔎 Veri çekiliyor ve analiz ediliyor...")

    try:
        msg, _ = await _run_analysis_threadsafe(symbol_raw, image_bytes)
        await _safe_edit(status, msg)
    except Exception as e:
        log.exception("Analiz hatası")
        await status.edit_text(f"⚠️ Analiz başarısız: {e}")


async def _run_analysis_threadsafe(symbol_raw: str, image_bytes: bytes | None):
    """Senkron ccxt/requests çağrılarını event loop'u bloklamadan çalıştırır."""
    symbol = data.normalize_symbol(symbol_raw)

    def work():
        ohlcv_by_tf = {}
        for tf in config.TIMEFRAMES:
            try:
                ohlcv_by_tf[tf] = data.fetch_ohlcv(symbol, tf, config.CANDLE_LIMIT)
            except Exception as e:
                log.warning("OHLCV alınamadı %s %s: %s", symbol, tf, e)
        if not ohlcv_by_tf:
            raise ValueError(
                f"'{symbol}' için veri alınamadı. Sembolü kontrol et (örn. BTC/USDT)."
            )
        summary = indicators.multi_timeframe_summary(symbol, ohlcv_by_tf)
        news_text = _fetch_news_text(symbol)
        result = analyzer.analyze(summary, image_bytes=image_bytes, news_text=news_text)
        return formatter.format_analysis(symbol, config.PRIMARY_TIMEFRAME, result)

    msg = await asyncio.to_thread(work)
    return msg, config.PRIMARY_TIMEFRAME


async def _route(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str,
                 image_bytes: bytes | None):
    """Tek kelimelik sembol → klasik kart; cümle → sohbet modu."""
    if _looks_like_bare_symbol(text):
        await _handle(update, ctx, text, image_bytes)
    else:
        await _handle_chat(update, ctx, text, image_bytes)


async def _handle_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str,
                       image_bytes: bytes | None):
    """Serbest metin (sohbet) isteğini işler."""
    user_id = update.effective_user.id
    if _rate_limited(user_id):
        await update.message.reply_text(
            f"⏳ Çok fazla istek. Dakikada {config.RATE_LIMIT_PER_MIN} sorgu sınırı var."
        )
        return

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    status = await update.message.reply_text(
        "💬 İsteğini anlıyorum, verileri çekip yorumluyorum..."
    )
    try:
        reply = await asyncio.to_thread(_run_chat, text, image_bytes)
        await _safe_edit(status, reply)
    except Exception as e:
        log.exception("Sohbet analizi hatası")
        await status.edit_text(f"⚠️ İsteğini işleyemedim: {e}")


def _run_chat(text: str, image_bytes: bytes | None) -> str:
    """Niyeti çözer, uygun veriyi çeker ve isteğe özel serbest yanıt üretir."""
    parsed = intent.parse(text)
    if not parsed.get("symbol"):
        return (
            "Hangi coin hakkında konuşmak istersin? Örn:\n"
            "_\"BTC'nin 3 aylık verisine bakıp tahmin yap\"_ ya da "
            "_\"ETH günlük trend nasıl?\"_"
        )
    symbol = data.normalize_symbol(parsed["symbol"])
    ohlcv = data.fetch_ohlcv(symbol, parsed["timeframe"], parsed["candle_limit"])
    summary = indicators.multi_timeframe_summary(symbol, {parsed["timeframe"]: ohlcv})
    if not summary["timeframes"]:
        raise ValueError(f"'{symbol}' için yeterli veri bulunamadı. Sembolü kontrol et.")
    news_text = _fetch_news_text(symbol)
    return analyzer.chat_analyze(parsed["request"], summary, image_bytes=image_bytes, news_text=news_text)


async def cmd_analiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    args = ctx.args or []
    symbol_raw = args[0] if args else ""
    # İkinci argüman zaman aralığı ise geçici override
    await _handle(update, ctx, symbol_raw, None)


_HABER_ON = {"ac", "aç", "on", "acik", "açık", "evet"}
_HABER_OFF = {"kapat", "off", "kapali", "kapalı", "hayir", "hayır"}


async def cmd_haber(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    global _news_enabled
    args = ctx.args or []
    if not args:
        durum = "açık ✅" if _news_enabled else "kapalı ❌"
        await update.message.reply_text(
            f"📰 Haber okuma şu an: *{durum}*\n"
            "Açmak için `/haber ac`, kapatmak için `/haber kapat` yaz.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    arg = args[0].strip().lower()
    if arg in _HABER_ON:
        _news_enabled = True
        await update.message.reply_text(
            "📰 Haber okuma açıldı — analizlerde güncel haber başlıkları da dikkate alınacak."
        )
    elif arg in _HABER_OFF:
        _news_enabled = False
        await update.message.reply_text(
            "📰 Haber okuma kapatıldı — analizler yalnızca teknik verilere dayanacak."
        )
    else:
        await update.message.reply_text(
            "Kullanım: `/haber ac` veya `/haber kapat`", parse_mode=ParseMode.MARKDOWN
        )


async def cmd_dogruluk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Kullanım: `/dogruluk BTC` veya `/dogruluk ETH 4h`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    user_id = update.effective_user.id
    if _rate_limited(user_id):
        await update.message.reply_text(
            f"⏳ Çok fazla istek. Dakikada {config.RATE_LIMIT_PER_MIN} sorgu sınırı var."
        )
        return

    symbol_raw = args[0]
    timeframe = args[1] if len(args) > 1 else config.PRIMARY_TIMEFRAME
    if timeframe not in config.TIMEFRAMES and timeframe not in (
        "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"
    ):
        timeframe = config.PRIMARY_TIMEFRAME

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    status = await update.message.reply_text(
        "🎯 Geçmiş noktalarda tahminler test ediliyor (biraz sürebilir)..."
    )
    try:
        result = await asyncio.to_thread(
            backtest.run_backtest, symbol_raw, timeframe
        )
        await _safe_edit(status, formatter.format_backtest(result))
    except Exception as e:
        log.exception("Backtest hatası")
        await status.edit_text(f"⚠️ Doğruluk analizi başarısız: {e}")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    text = (update.message.text or "").strip()
    if _is_help_text(text):
        await update.message.reply_text(
            WELCOME.format(name=config.BOT_NAME), parse_mode=ParseMode.MARKDOWN
        )
        return
    await _route(update, ctx, text, None)


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await _guard(update):
        return
    caption = (update.message.caption or "").strip()
    photo = update.message.photo[-1]  # en yüksek çözünürlük
    file = await photo.get_file()
    buf = await file.download_as_bytearray()
    image_bytes = bytes(buf)
    if not caption:
        await update.message.reply_text(
            "🖼️ Görsel alındı ama hangi coin? Caption'a coin adını (veya isteğini) yaz "
            "(örn. `BTC/USDT` ya da _\"BTC bu grafikte ne diyor?\"_).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await _route(update, ctx, caption, image_bytes)


def main():
    problems = config.validate()
    if problems:
        for p in problems:
            log.error("Yapılandırma hatası: %s", p)
        log.error("Lütfen .env dosyasını doldurun.")
        raise SystemExit(1)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("analiz", cmd_analiz))
    app.add_handler(CommandHandler("dogruluk", cmd_dogruluk))
    app.add_handler(CommandHandler("haber", cmd_haber))
    app.add_handler(CommandHandler("yardim", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot başlıyor (model=%s, borsa=%s)...", config.LLM_MODEL, config.EXCHANGE_ID)
    if config.ALLOWED_USER_IDS:
        log.info("Özel mod açık: yalnızca %s erişebilir.", config.ALLOWED_USER_IDS)
    else:
        log.info("Bot herkese açık (ALLOWED_USER_IDS boş).")
    if config.BOT_PERSONA:
        log.info("Kişilik ayarlı: %s", config.BOT_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
