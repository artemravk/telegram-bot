import os
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# === Настройки ===
EXPRESS_PAY_TOKEN = os.getenv("EXPRESS_PAY_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")  # URL приложения на Render
API_URL = "https://api.express-pay.by/v1/invoices"

# === Главное меню ===
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите действие:", reply_markup=main_menu())

# === Обработка нажатий кнопок ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например: 25,50):")
        context.user_data["action"] = "create_invoice"
    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта (в формате 35077-1-XXX):")
        context.user_data["action"] = "check_status"
    elif query.data == "main_menu":
        await query.message.reply_text("Выберите действие:", reply_markup=main_menu())

# === Счётчик AccountNo ===
account_counter_file = "account_counter.txt"

def get_next_account_no():
    if not os.path.exists(account_counter_file):
        with open(account_counter_file, "w") as f:
            f.write("1")
        return 1
    with open(account_counter_file, "r+") as f:
        current = int(f.read().strip() or 0)
        new = current + 1
        f.seek(0)
        f.write(str(new))
        f.truncate()
        return new

# === Обработка сообщений пользователя ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        amount = update.message.text.strip()
        account_no = f"35077-1-{get_next_account_no()}"

        data = {
            "Token": EXPRESS_PAY_TOKEN,
            "AccountNo": account_no,
            "Amount": amount,
            "Currency": 933,
            "Info": "организация доставки"
        }

        response = requests.post(f"{API_URL}?token={EXPRESS_PAY_TOKEN}", data=data)

        if response.status_code == 200:
            invoice_no = response.json().get("InvoiceNo")

            # Получаем детальную информацию о счёте
            detail_response = requests.get(f"{API_URL}/{invoice_no}?token={EXPRESS_PAY_TOKEN}")
            if detail_response.status_code == 200:
                info = detail_response.json()
                amount_info = info.get("Amount")
                account_info = info.get("AccountNo")
                account_display = f"35077-1-{account_info.split('-')[-1]}" if '-' in account_info else account_info

                await update.message.reply_text(
                    f"✅ Счёт на {amount_info} рублей выставлен.\n"
                    f"Номер счёта: `{account_display}`",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
            else:
                await update.message.reply_text(
                    f"❌ Ошибка при получении информации о счёте.\n{detail_response.text}"
                )
        else:
            await update.message.reply_text(f"❌ Ошибка при выставлении счёта:\n{response.text}")

        context.user_data.pop("action", None)

    elif action == "check_status":
        account_no = update.message.text.strip()
        response = requests.get(f"{API_URL}/by-accountno/{account_no}?token={EXPRESS_PAY_TOKEN}")

        if response.status_code == 200:
            data = response.json()
            status = data.get("Status")
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
                f"📊 Статус счёта {account_no}: {statuses.get(status, 'Неизвестен')}",
                reply_markup=main_menu()
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
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
