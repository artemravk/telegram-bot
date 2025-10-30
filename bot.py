import os
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --------------------- НАСТРОЙКИ ---------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram токен
API_TOKEN = os.getenv("EXPRESSPAY_TOKEN")  # ExpressPay токен
APP_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render сам подставит
BASE_URL = "https://api.express-pay.by/v1/invoices"

# -----------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}  # временные данные по пользователям


# --------------------- EXPRESSPAY ---------------------

def create_invoice(amount: float):
    """Создание счёта в ExpressPay"""

    # Генерируем AccountNo в нужном формате: DDMMYY + порядковый номер
    today = datetime.now().strftime("%d%m%y")
    order_number = 1  # если нужно, можно позже хранить и увеличивать
    account_no = f"{today}{order_number:03d}"

    payload = {
        "AccountNo": account_no,
        "Amount": str(amount).replace('.', ','),
        "Currency": 933,
        "Info": "организация доставки",
    }

    # ✅ ВОТ ТАК БЫЛО В РАБОЧЕМ ВАРИАНТЕ — токен в URL
    url = f"{BASE_URL}?token={API_TOKEN}"
    response = requests.post(url, json=payload)
    return response.status_code, response.text


def get_invoice_status(invoice_no: int):
    """Проверка статуса счёта"""
    url = f"{BASE_URL}/{invoice_no}/status?token={API_TOKEN}"
    response = requests.get(url)
    return response.status_code, response.text


# --------------------- TELEGRAM ---------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📄 Статус счёта", callback_data="check_status")],
    ]
    await update.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например, 25.50):")
        user_state[query.from_user.id] = "create_invoice"
    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта:")
        user_state[query.from_user.id] = "check_status"


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    state = user_state.get(user_id)

    if state == "create_invoice":
        try:
            amount = float(update.message.text.replace(',', '.'))
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")
            return

        status_code, response_text = create_invoice(amount)
        if status_code in (200, 201):
            await update.message.reply_text(f"✅ Счёт успешно создан!\n{response_text}")
        else:
            await update.message.reply_text(f"❌ Ошибка при создании счёта.\nКод: {status_code}\nОтвет: {response_text}")

    elif state == "check_status":
        try:
            invoice_no = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ Введите корректный номер счёта.")
            return

        status_code, response_text = get_invoice_status(invoice_no)
        if status_code == 200:
            await update.message.reply_text(f"📄 Статус счёта:\n{response_text}")
        else:
            await update.message.reply_text(f"❌ Ошибка при получении статуса.\nКод: {status_code}\nОтвет: {response_text}")

    else:
        await update.message.reply_text("Введите /start, чтобы начать.")


# --------------------- MAIN ---------------------

def main():
    if not BOT_TOKEN or not API_TOKEN:
    raise ValueError("❌ Проверьте, что заданы BOT_TOKEN и EXPRESSPAY_TOKEN")

# Render может подставить RENDER_EXTERNAL_URL чуть позже, поэтому делаем fallback
if not APP_URL:
    logger.warning("⚠️ Переменная RENDER_EXTERNAL_URL не найдена. Используется временный URL-заглушка.")
    APP_URL = "https://example.com"

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Webhook для Render
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()
