import os
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --------------------- НАСТРОЙКИ ---------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен Telegram-бота
API_TOKEN = os.getenv("EXPRESSPAY_TOKEN")  # Токен ExpressPay
APP_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render автоматически подставляет URL

BASE_URL = "https://api.express-pay.by/v1"

# -----------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Счётчики для AccountNo
order_counter = 1
invoice_temp_data = {}  # временные данные по пользователям


# --------------------- ФУНКЦИИ EXPRESSPAY ---------------------

def create_invoice(amount: float):
    """Выставление счёта"""
    global order_counter
    account_no = datetime.now().strftime("%d%m%y") + str(order_counter).zfill(3)
    order_counter += 1

    payload = {
        "AccountNo": account_no,
        "Amount": str(amount).replace('.', ','),
        "Currency": 933,
        "Info": "организация доставки"
    }

    url = f"{BASE_URL}/invoices?token={API_TOKEN}"
    response = requests.post(url, json=payload)
    return response.status_code, response.text


def get_invoice_status(invoice_no: int):
    """Получение статуса счёта"""
    url = f"{BASE_URL}/invoices/{invoice_no}/status?token={API_TOKEN}"
    response = requests.get(url)
    return response.status_code, response.text


# --------------------- ОБРАБОТЧИКИ ---------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📄 Статус счёта", callback_data="check_status")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например, 25.50):")
        context.user_data["action"] = "create_invoice"

    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта для проверки статуса:")
        context.user_data["action"] = "check_status"


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        try:
            amount = float(update.message.text.replace(',', '.'))
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму, например 25.50")
            return

        status_code, response_text = create_invoice(amount)
        if status_code == 200 or status_code == 201:
            await update.message.reply_text(f"✅ Счёт успешно выставлен!\nОтвет: {response_text}")
        else:
            await update.message.reply_text(f"❌ Ошибка при выставлении счёта.\nКод: {status_code}\nТекст: {response_text}")

    elif action == "check_status":
        try:
            invoice_no = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ Введите числовой номер счёта.")
            return

        status_code, response_text = get_invoice_status(invoice_no)
        if status_code == 200:
            await update.message.reply_text(f"📄 Статус счёта:\n{response_text}")
        else:
            await update.message.reply_text(f"❌ Ошибка при получении статуса.\nКод: {status_code}\nТекст: {response_text}")

    else:
        await update.message.reply_text("Выберите действие через /start.")


# --------------------- MAIN ---------------------

def main():
    if not BOT_TOKEN or not API_TOKEN or not APP_URL:
        raise ValueError("❌ Проверьте, что заданы переменные окружения BOT_TOKEN, EXPRESSPAY_TOKEN и RENDER_EXTERNAL_URL")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Для Render — webhook вместо polling
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()
