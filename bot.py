import os
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# === Настройки ===
EXPRESS_PAY_TOKEN = os.getenv("EXPRESS_PAY_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")  # URL приложения на Render, например https://my-bot.onrender.com
API_URL = "https://api.express-pay.by/v1/invoices"


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")]
    ]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# === Обработка нажатий кнопок ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например: 25,50):")
        context.user_data["action"] = "create_invoice"
    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта:")
        context.user_data["action"] = "check_status"


# === Функция для получения детальной информации о счёте ===
def get_invoice_details(invoice_no: int):
    """Возвращает детальную информацию по счёту из ExpressPay."""
    url = f"{API_URL}/{invoice_no}?token={EXPRESS_PAY_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


# === Обработка сообщений пользователя ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        amount = update.message.text.strip().replace(",", ".")
        today = datetime.now().strftime("%d%m%y")
        account_no = f"{today}001"
        data = {
            "Token": EXPRESS_PAY_TOKEN,
            "AccountNo": account_no,
            "Amount": amount,
            "Currency": 933,
            "Info": "организация доставки"
        }

        # Создаём счёт
        response = requests.post(f"{API_URL}?token={EXPRESS_PAY_TOKEN}", data=data)
        if response.status_code == 200:
            invoice_no = response.json().get("InvoiceNo")

            # Получаем детальную информацию по счёту
            details = get_invoice_details(invoice_no)
            if details:
                amount_info = details.get("Amount")
                account_info = details.get("AccountNo")
                await update.message.reply_text(
                    f"✅ Счёт на {amount_info} рублей выставлен.\n"
                    f"Номер счёта: 35077-1-{account_info}"
                )
            else:
                await update.message.reply_text(
                    f"✅ Счёт выставлен, но не удалось получить детали.\n"
                    f"InvoiceNo: {invoice_no}"
                )
        else:
            await update.message.reply_text(f"❌ Ошибка при выставлении счёта:\n{response.text}")

        context.user_data.pop("action", None)

    elif action == "check_status":
        invoice_no = update.message.text.strip()
        response = requests.get(f"{API_URL}/{invoice_no}/status?token={EXPRESS_PAY_TOKEN}")
        if response.status_code == 200:
            status = response.json().get("Status")
            statuses = {
                1: "Ожидает оплату",
                2: "Просрочен",
                3: "Оплачен",
                4: "Оплачен частично",
                5: "Отменен",
                6: "Оплачен картой",
                7: "Платёж возвращен"
            }
            await update.message.reply_text(
                f"📊 Статус счёта {invoice_no}: {statuses.get(status, 'Неизвестен')}"
            )
        else:
            await update.message.reply_text(f"❌ Ошибка при получении статуса:\n{response.text}")

        context.user_data.pop("action", None)


# === Основная функция ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 8443))

    # Настройка Webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}"
    )


if __name__ == "__main__":
    main()
