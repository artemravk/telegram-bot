import os
import hmac
import hashlib
import json
import logging
import requests
from aiohttp import web
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
EXPRESSPAY_TOKEN = os.getenv("EXPRESSPAY_TOKEN")
EXPRESSPAY_SECRET = os.getenv("EXPRESSPAY_SECRET")
APP_URL = os.getenv("APP_URL")

if not BOT_TOKEN or not EXPRESSPAY_TOKEN:
    raise ValueError("❌ Проверьте, что заданы BOT_TOKEN и EXPRESSPAY_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === КНОПКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("Статус счёта", callback_data="check_status")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# === ОБРАБОТКА КНОПОК ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (в BYN):")
        context.user_data["action"] = "create_invoice"

    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта (в формате 35077-1-XXXX):")
        context.user_data["action"] = "check_status"

# === СООБЩЕНИЯ ОТ ПОЛЬЗОВАТЕЛЯ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    # === СОЗДАНИЕ СЧЁТА ===
    if action == "create_invoice":
        amount = update.message.text.strip()
        if not amount.replace(".", "", 1).isdigit():
            await update.message.reply_text("Введите корректную сумму (например, 12.50)")
            return

        account_info = "301025001"  # тестовый номер счёта
        account_no = f"35077-1-{account_info}"

        url = "https://api.express-pay.by/v1/invoices"
        data = {
            "Token": EXPRESSPAY_TOKEN,
            "ServiceId": 35077,
            "AccountNo": account_info,
            "Amount": amount,
            "Currency": 933,
            "Info": "Оплата услуг",
        }

        response = requests.post(url, data=data)
        resp_json = response.json()
        logger.info(f"Invoice creation response: {resp_json}")

        if "InvoiceNo" in resp_json:
            text = (
                f"✅ Счёт выставлен!\n\n"
                f"Номер счёта: `35077-1-{account_info}`\n"
                f"Сумма: {amount} BYN\n\n"
                f"Скопируйте номер счёта для проверки статуса."
            )
        else:
            text = f"Ошибка при создании счёта: {resp_json}"

        await update.message.reply_text(text, parse_mode="Markdown")
        context.user_data["action"] = None

    # === ПРОВЕРКА СТАТУСА СЧЁТА ===
    elif action == "check_status":
        account_no = update.message.text.strip()
        if not account_no.startswith("35077-1-"):
            await update.message.reply_text("Неверный формат счёта. Пример: 35077-1-301025001")
            return

        account_info = account_no.split("-")[-1]

        url = f"https://api.express-pay.by/v1/invoices?Token={EXPRESSPAY_TOKEN}&AccountNo={account_info}"
        response = requests.get(url)
        resp_json = response.json()

        logger.info(f"ExpressPay raw response: {resp_json}")

        if "Items" in resp_json and len(resp_json["Items"]) > 0:
            invoice = resp_json["Items"][-1]
            status_code = invoice.get("Status", 0)
            status_map = {1: "Выставлен", 2: "Оплачен", 3: "Просрочен", 4: "Отменён"}
            status = status_map.get(status_code, "Неизвестен")

            created_raw = invoice.get("Created")
            created_date = (
                datetime.strptime(created_raw, "%Y%m%d%H%M%S").strftime("%d.%m.%Y %H:%M")
                if created_raw
                else "—"
            )

            amount = invoice.get("Amount", "—")
            currency = "BYN"

            text = (
                f"📊 Статус счёта\n\n"
                f"Номер: {account_no}\n"
                f"Статус: {status}\n"
                f"Сумма: {amount} {currency}\n"
                f"Дата выставления: {created_date}"
            )
        else:
            text = f"⚠️ Счёт с номером {account_no} не найден."

        await update.message.reply_text(text)
        context.user_data["action"] = None

# === ОБРАБОТКА УВЕДОМЛЕНИЙ ОПЛАТЫ ===
async def expresspay_notify(request: web.Request):
    try:
        post_data = await request.post()
        data_raw = post_data.get("Data")
        signature = post_data.get("Signature")

        if not data_raw:
            return web.Response(status=400, text="Missing Data")

        data = json.loads(data_raw)

        # Проверка подписи, если задан секрет
        if EXPRESSPAY_SECRET and signature:
            computed = hmac.new(
                EXPRESSPAY_SECRET.encode("utf-8"),
                msg=data_raw.encode("utf-8"),
                digestmod=hashlib.sha1,
            ).hexdigest().upper()

            if computed != signature:
                logger.warning("⚠️ Подпись не совпадает")
                return web.Response(status=400, text="Invalid signature")

        logger.info(f"💰 Получено уведомление о платеже: {data}")
        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"❌ Ошибка при обработке уведомления: {e}")
        return web.Response(status=500, text="Error")

# === ЗАПУСК ===
def main():
    print("🔍 Проверка переменных окружения:")
    print(f"BOT_TOKEN: {'✅ найден' if BOT_TOKEN else '❌ отсутствует'}")
    print(f"EXPRESSPAY_TOKEN: {'✅ найден' if EXPRESSPAY_TOKEN else '❌ отсутствует'}")
    print(f"EXPRESSPAY_SECRET: {'✅ найден' if EXPRESSPAY_SECRET else '⚠️ отсутствует'}")
    print(f"APP_URL: {APP_URL}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Telegram обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Aiohttp сервер для уведомлений ExpressPay
    web_app = web.Application()
    web_app.router.add_post("/expresspay_notify", expresspay_notify)

    # Запуск Telegram webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}",
        web_app=web_app,
    )

if __name__ == "__main__":
    main()
