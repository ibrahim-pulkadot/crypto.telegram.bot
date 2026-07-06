"""Telegram kripto analiz botu — giriş noktası."""
import asyncio
import logging
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("cryptobot")

# Kullanıcı başına istek zaman damgaları (basit rate-limit)
_requests: dict[int, deque] = defaultdict(deque)


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    dq = _requests[user_id]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= config.RATE_LIMIT_PER_MIN:
        return True
    dq.append(now)
    return False


WELCOME = (
    "👋 *Kripto Analiz Botu*\n\n"
    "Bir coin gönder, teknik analiz + AI yorumu çıkarayım.\n\n"
    "*Kullanım:*\n"
    "• `BTC` veya `BTC/USDT` yaz\n"
    "• `/analiz ETH 4h`\n"
    "• Bir grafik görseli gönder (caption'a coin adını yaz), hem görseli hem "
    "gerçek veriyi birlikte analiz edeyim\n"
    "• `/dogruluk BTC 4h` — AI tahminlerinin geçmişteki isabet oranını ölç\n\n"
    "⚠️ _Yatırım tavsiyesi değildir._"
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)


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
        await status.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
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
        result = analyzer.analyze(summary, image_bytes=image_bytes)
        return formatter.format_analysis(symbol, config.PRIMARY_TIMEFRAME, result)

    msg = await asyncio.to_thread(work)
    return msg, config.PRIMARY_TIMEFRAME


async def cmd_analiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    symbol_raw = args[0] if args else ""
    # İkinci argüman zaman aralığı ise geçici override
    await _handle(update, ctx, symbol_raw, None)


async def cmd_dogruluk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        await status.edit_text(
            formatter.format_backtest(result), parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        log.exception("Backtest hatası")
        await status.edit_text(f"⚠️ Doğruluk analizi başarısız: {e}")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    await _handle(update, ctx, text, None)


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    caption = (update.message.caption or "").strip()
    photo = update.message.photo[-1]  # en yüksek çözünürlük
    file = await photo.get_file()
    buf = await file.download_as_bytearray()
    image_bytes = bytes(buf)
    if not caption:
        await update.message.reply_text(
            "🖼️ Görsel alındı ama hangi coin? Caption'a coin adını yaz "
            "(örn. görselle birlikte `BTC/USDT`).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await _handle(update, ctx, caption, image_bytes)


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
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot başlıyor (model=%s, borsa=%s)...", config.LLM_MODEL, config.EXCHANGE_ID)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
