import os
import json
import hmac
import hashlib
import logging
from datetime import datetime
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from aiohttp import web

# === НАСТРОЙКИ ===
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
EXPRESS_PAY_TOKEN = os.getenv("EXPRESSPAY_TOKEN")
EXPRESS_PAY_SECRET = os.getenv("EXPRESSPAY_SECRET")
APP_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_URL")  # на случай, если у тебя была app_url

print("🔍 Проверка переменных окружения:")
print("BOT_TOKEN:", "✅ найден" if BOT_TOKEN else "❌ отсутствует")
print("EXPRESSPAY_TOKEN:", "✅ найден" if EXPRESS_PAY_TOKEN else "❌ отсутствует")
print("EXPRESSPAY_SECRET:", "✅ найден" if EXPRESS_PAY_SECRET else "❌ отсутствует")
print("APP_URL:", APP_URL or "❌ отсутствует")

if not BOT_TOKEN or not EXPRESS_PAY_TOKEN:
    raise ValueError("❌ Проверьте, что заданы BOT_TOKEN и EXPRESSPAY_TOKEN")



# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}
current_account_number = 1


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")],
    ]
    await update.message.reply_text(
        "Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


# === Обработка кнопок ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        user_state[query.from_user.id] = "creating_invoice"
        await query.message.reply_text("Введите сумму счёта (BYN):")

    elif query.data == "check_status":
        user_state[query.from_user.id] = "checking_status"
        await query.message.reply_text("Введите номер счёта (формат: 35077-1-XXXXXXX)")


# === Обработка текстовых сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    action = user_state.get(user_id)

    global current_account_number

    if action == "creating_invoice":
        try:
            amount = float(update.message.text.strip().replace(",", "."))
        except ValueError:
            await update.message.reply_text("Введите корректную сумму.")
            return

        account_no = f"301025{current_account_number:03d}"
        current_account_number += 1

        payload = {
            "Token": EXPRESSPAY_TOKEN,
            "AccountNo": account_no,
            "Amount": amount,
            "Currency": 933,
        }

        response = requests.post(EXPRESSPAY_URL, data=payload)
        data = response.json()

        invoice_no = data.get("InvoiceNo")
        if invoice_no:
            msg = (
                f"✅ Счёт успешно создан!\n\n"
                f"💳 Номер счёта: `35077-1-{account_no}`\n"
                f"💰 Сумма: {amount:.2f} BYN\n\n"
                f"Номер можно скопировать вручную."
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Ошибка при создании счёта.")

    elif action == "checking_status":
        user_input = update.message.text.strip()
        if "-" in user_input:
            account_no = user_input.split("-")[-1]
        else:
            account_no = user_input

        params = {"Token": EXPRESSPAY_TOKEN, "AccountNo": account_no}
        resp = requests.get(EXPRESSPAY_URL, params=params)
        raw_json = resp.json()

        items = raw_json.get("Items", [])
        if not items:
            await update.message.reply_text("Счёт не найден.")
            return

        invoice = items[-1]
        created_raw = invoice.get("Created")
        created_date = datetime.strptime(created_raw, "%Y%m%d%H%M%S").strftime("%d.%m.%Y %H:%M:%S")
        status = invoice.get("Status")

        status_text = {
            1: "🕓 Ожидает оплаты",
            2: "✅ Оплачен",
            3: "❌ Отменён",
        }.get(status, "Неизвестен")

        msg = (
            f"📊 Статус счёта\n\n"
            f"Номер: 35077-1-{invoice.get('AccountNo')}\n"
            f"Статус: {status_text}\n"
            f"Сумма: {invoice.get('Amount')} BYN\n"
            f"Дата выставления: {created_date}"
        )

        await update.message.reply_text(msg)

    user_state[user_id] = None


# === Обработчик уведомлений ExpressPay ===
async def expresspay_notification(request):
    try:
        data = await request.post()
        json_data = data.get("Data")
        signature = data.get("Signature")

        if not json_data:
            return web.Response(status=400, text="Missing Data")

        # Проверяем подпись
        if EXPRESSPAY_SECRET:
            computed = hmac.new(
                EXPRESSPAY_SECRET.encode(),
                msg=json_data.encode(),
                digestmod=hashlib.sha1
            ).hexdigest().upper()
            if computed != signature:
                logger.warning("❌ Подпись не совпадает")
                return web.Response(status=403, text="Invalid signature")

        payment_info = json.loads(json_data)
        logger.info(f"✅ Поступило уведомление о платеже: {payment_info}")

        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"❌ Ошибка при обработке уведомления: {e}")
        return web.Response(status=500, text="Server error")


# === Главная функция ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Добавляем HTTP endpoint для ExpressPay уведомлений
    from aiohttp import web
    web_app = web.Application()
    web_app.router.add_post("/expresspay_notify", expresspay_notification)

    # Запуск Telegram webhook + HTTP-сервера
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_URL', 'yourapp.onrender.com')}/{BOT_TOKEN}",
    )

    web.run_app(web_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
