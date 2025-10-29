import os
import logging
from datetime import datetime
import requests
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ------------------- НАСТРОЙКИ -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")  # токен Telegram-бота
API_TOKEN = os.getenv("API_TOKEN")  # токен ExpressPay
APP_URL = os.getenv("APP_URL")      # URL Render-приложения (https://my-bot.onrender.com)
EXPRESS_URL = "https://api.express-pay.by/v1/invoices"

# Этапы диалога
ASK_AMOUNT = 1
ASK_INVOICE_NO = 2


# ------------------- /start -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("💰 Выставить счёт"), KeyboardButton("📄 Статус счёта")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Привет! Я бот для работы с ExpressPay.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )


# ------------------- 1. Выставление счёта -------------------
async def invoice_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите сумму счёта (например, 25.50):")
    return ASK_AMOUNT


async def create_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text.strip().replace(".", ",")  # ExpressPay требует запятую
    date_str = datetime.now().strftime("%d%m%y")
    order_no = "001"
    account_no = f"{date_str}{order_no}"

    payload = {
        "AccountNo": account_no,
        "Amount": amount,
        "Currency": 933,
        "Info": "организация доставки"
    }

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(EXPRESS_URL, json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()
            invoice_no = data.get("InvoiceNo")
            await update.message.reply_text(
                f"✅ Счёт успешно выставлен!\n\n"
                f"🔸 Номер счёта в ExpressPay: {invoice_no}\n"
                f"🔹 Ваш номер счёта (AccountNo): {account_no}"
            )
        else:
            await update.message.reply_text(
                f"❌ Ошибка при выставлении счёта.\n"
                f"Код: {response.status_code}\n"
                f"Текст: {response.text}"
            )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка соединения: {e}")

    return ConversationHandler.END


# ------------------- 2. Проверка статуса счёта -------------------
async def status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите номер счёта (InvoiceNo):")
    return ASK_INVOICE_NO


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    invoice_no = update.message.text.strip()
    url = f"{EXPRESS_URL}/{invoice_no}?cmd=status"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            status_code = data.get("Status")

            statuses = {
                1: "⏳ Ожидает оплату",
                2: "⚠️ Просрочен",
                3: "✅ Оплачен",
                4: "💵 Оплачен частично",
                5: "❌ Отменён",
                6: "💳 Оплачен картой",
                7: "↩️ Платёж возвращён"
            }

            status_text = statuses.get(status_code, "Неизвестный статус")
            await update.message.reply_text(f"Статус счёта №{invoice_no}: {status_text}")
        else:
            await update.message.reply_text(
                f"❌ Ошибка при получении статуса.\n"
                f"Код: {response.status_code}\n"
                f"Текст: {response.text}"
            )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка соединения: {e}")

    return ConversationHandler.END


# ------------------- Отмена -------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


# ------------------- MAIN -------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    invoice_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("(^💰 Выставить счёт$)"), invoice_start)],
        states={ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_invoice)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    status_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("(^📄 Статус счёта$)"), status_start)],
        states={ASK_INVOICE_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_status)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(invoice_conv)
    app.add_handler(status_conv)

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}"
    )


if __name__ == "__main__":
    main()
