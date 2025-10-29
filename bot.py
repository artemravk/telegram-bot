import os
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

EXPRESS_PAY_TOKEN = os.getenv("EXPRESS_PAY_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.express-pay.by/v1/invoices"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")]
    ]
    await update.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например: 25,50):")
        context.user_data["action"] = "create_invoice"
    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта:")
        context.user_data["action"] = "check_status"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        amount = update.message.text.strip()
        today = datetime.now().strftime("%d%m%y")
        account_no = f"{today}001"
        data = {
            "Token": EXPRESS_PAY_TOKEN,
            "AccountNo": account_no,
            "Amount": amount,
            "Currency": 933,
            "Info": "организация доставки"
        }
        r = requests.post(f"{API_URL}?token={EXPRESS_PAY_TOKEN}", data=data)
        if r.status_code == 200:
            invoice_no = r.json().get("InvoiceNo")
            await update.message.reply_text(f"✅ Счёт выставлен!\nНомер счёта: {invoice_no}")
        else:
            await update.message.reply_text(f"❌ Ошибка: {r.text}")
        context.user_data.pop("action", None)

    elif action == "check_status":
        invoice_no = update.message.text.strip()
        r = requests.get(f"{API_URL}/{invoice_no}/status?token={EXPRESS_PAY_TOKEN}")
        if r.status_code == 200:
            status = r.json().get("Status")
            statuses = {
                1: "Ожидает оплату",
                2: "Просрочен",
                3: "Оплачен",
                4: "Оплачен частично",
                5: "Отменен",
                6: "Оплачен картой",
                7: "Платёж возвращен"
            }
            await update.message.reply_text(f"📊 Статус счёта {invoice_no}: {statuses.get(status, 'Неизвестен')}")
        else:
            await update.message.reply_text(f"❌ Ошибка: {r.text}")
        context.user_data.pop("action", None)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
