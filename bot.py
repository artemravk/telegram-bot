import os
import hmac
import hashlib
import json
import asyncio
import logging
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
EXPRESSPAY_TOKEN = os.environ.get("EXPRESSPAY_TOKEN")
EXPRESSPAY_SECRET = os.environ.get("EXPRESSPAY_SECRET")
APP_URL = os.environ.get("APP_URL")

if not BOT_TOKEN or not EXPRESSPAY_TOKEN:
    raise ValueError("❌ Проверьте, что заданы BOT_TOKEN и EXPRESSPAY_TOKEN")

# === СТАРТ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Статус счёта", callback_data="status")],
        [InlineKeyboardButton("📄 Инструкция", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Выберите действие:", reply_markup=reply_markup)

# === КНОПКИ ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "status":
        invoice_number = "123456"
        issue_date = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        text = f"📄 Номер счёта: {invoice_number}\n🗓 Дата выставления: {issue_date}"
        await query.edit_message_text(text)
    elif query.data == "help":
        await query.edit_message_text("ℹ️ Чтобы проверить статус счёта, нажмите 'Статус счёта'.")

# === ОБРАБОТКА СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if "счет" in text or "инвойс" in text:
        await update.message.reply_text("Проверяю статус счёта...")
    else:
        await update.message.reply_text("Я вас не понял. Напишите 'счёт' чтобы проверить статус.")

# === ВЕБХУК EXPRESSPAY ===
async def expresspay_notify(request):
    try:
        body = await request.text()
        logger.info(f"📩 ExpressPay уведомление: {body}")

        # Проверка подписи
        if EXPRESSPAY_SECRET:
            signature = request.headers.get("Signature", "")
            expected_sig = hmac.new(
                EXPRESSPAY_SECRET.encode(), body.encode(), hashlib.sha1
            ).hexdigest()
            if signature != expected_sig:
                logger.warning("❌ Неверная подпись уведомления ExpressPay")
                return web.Response(status=403, text="Invalid signature")

        data = json.loads(body)
        logger.info(f"✅ Уведомление от ExpressPay обработано: {data}")
        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"Ошибка обработки ExpressPay уведомления: {e}")
        return web.Response(status=500, text="Internal server error")

# === ВЕБХУК TELEGRAM ===
async def telegram_webhook(request):
    try:
        data = await request.json()
        update = Update.de_json(data, request.app["bot"])

        # Инициализация приложения перед обработкой апдейта
        app = request.app["application"]
        if not app._initialized:
            await app.initialize()

        await app.process_update(update)
        return web.Response(text="OK")

    except Exception as e:
        logger.exception(f"Ошибка в telegram_webhook: {e}")
        return web.Response(status=500, text="Internal Server Error")

# === ОСНОВНОЙ ЗАПУСК ===
async def main():
    print("🔍 Проверка переменных окружения:")
    print(f"BOT_TOKEN: {'✅ найден' if BOT_TOKEN else '❌ отсутствует'}")
    print(f"EXPRESSPAY_TOKEN: {'✅ найден' if EXPRESSPAY_TOKEN else '❌ отсутствует'}")
    print(f"EXPRESSPAY_SECRET: {'✅ найден' if EXPRESSPAY_SECRET else '⚠️ отсутствует'}")
    print(f"APP_URL: {APP_URL}")

    # Инициализация Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # === aiohttp сервер ===
    web_app = web.Application()
    web_app["bot"] = application.bot
    web_app["application"] = application

    # Роуты
    web_app.router.add_post(f"/{BOT_TOKEN}", telegram_webhook)
    web_app.router.add_post("/expresspay_notify", expresspay_notify)

    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    # === Установка вебхука Telegram ===
    if APP_URL:
        webhook_url = f"{APP_URL}/{BOT_TOKEN}"
        await application.bot.set_webhook(webhook_url)
        print(f"✅ Webhook Telegram установлен: {webhook_url}")
    else:
        print("⚠️ APP_URL не задан, Telegram webhook не установлен")

    print(f"🚀 Сервер запущен на порту {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
