import os
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# === Настройки ===
EXPRESS_PAY_TOKEN = os.getenv("EXPRESS_PAY_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
API_URL = "https://api.express-pay.by/v1/invoices"
PAYMENTS_API_URL = "https://api.express-pay.by/v1/payments"  # ✅ новое
ACCOUNT_FILE = "account_no.txt"


# === Главное меню ===
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")],
        [InlineKeyboardButton("📅 Получить список оплат", callback_data="get_payments")]  # ✅ новая кнопка
    ])


# === Функция получения суммы оплат ===
def get_payments_sum(token: str, date_from: str = None, date_to: str = None):
    """
    Возвращает общую сумму оплат за заданный период.
    Если даты не указаны — берём предыдущий день.
    Формат дат: yyyyMMdd
    """
    if not date_from or not date_to:
        yesterday = datetime.now() - timedelta(days=1)
        date_from = yesterday.strftime("%Y%m%d")
        date_to = yesterday.strftime("%Y%m%d")

    params = {
        "token": token,
        "From": date_from,
        "To": date_to
    }

    response = requests.get(PAYMENTS_API_URL, params=params)

    if response.status_code != 200:
        return None, f"Ошибка {response.status_code}: {response.text}"

    try:
        data = response.json()
    except Exception:
        return None, "Некорректный JSON-ответ от ExpressPay."

    if "Error" in data:
        return None, data["Error"].get("Msg", "Неизвестная ошибка")

    items = data.get("Items", [])
    total_amount = sum(float(item.get("Amount", 0)) for item in items)

    return total_amount, None


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите действие:", reply_markup=main_menu())


# === Обработка кнопок ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        await query.message.reply_text("Выберите действие:", reply_markup=main_menu())

    elif query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например: 25,50):")
        context.user_data["action"] = "create_invoice"

    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта:")
        context.user_data["action"] = "check_status"

    elif query.data == "get_payments":  # ✅ новая ветка
        await query.message.reply_text("Получаю список оплат за вчера...")
        total, error = get_payments_sum(EXPRESS_PAY_TOKEN)
        if error:
            await query.message.reply_text(f"❌ Ошибка: {error}", reply_markup=main_menu())
        else:
            await query.message.reply_text(
                f"📅 Общая сумма оплат за вчера: *{total:.2f} BYN*",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )


# === Остальная логика handle_message и main — без изменений ===
# (оставляем как есть из твоего оригинального кода)
