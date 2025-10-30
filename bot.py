import os
import logging
import requests
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ ИЗ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_TOKEN = os.getenv("EXPRESSPAY_TOKEN")
APP_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN or not API_TOKEN:
    raise ValueError("❌ Проверьте, что заданы BOT_TOKEN и EXPRESSPAY_TOKEN")

# Render иногда не задаёт URL сразу — подстрахуемся:
if not APP_URL:
    logger.warning("⚠️ Переменная RENDER_EXTERNAL_URL не найдена. Используется временный URL-заглушка.")
    APP_URL = "https://example.com"

# --- ОСНОВНЫЕ ФУНКЦИИ ---
def create_invoice(amount: str):
    """Создаёт счёт через ExpressPay API."""
    try:
        account_no = datetime.now().strftime("%d%m%y") + "001"
        payload = {
            "AccountNo": account_no,
            "Amount": amount.replace(".", ","),
            "Currency": 933,
            "Info": "организация доставки"
        }

        url = f"https://api.express-pay.by/v1/invoices?token={API_TOKEN}"
        response = requests.post(url, json=payload)

        if response.status_code == 200:
            data = response.json()
            invoice_no = data.get("InvoiceNo", "неизвестно")
            return f"✅ Счёт успешно выставлен.\nНомер счёта: {invoice_no}\nВаш AccountNo: {account_no}"
        else:
            return f"❌ Ошибка при выставлении счёта.\nКод: {response.status_code}\nТекст: {response.text}"
    except Exception as e:
        return f"⚠️ Ошибка при выставлении счёта: {e}"

def get_invoice_status(invoice_no: str):
    """Проверяет статус счёта."""
    try:
        url = f"https://api.express-pay.by/v1/invoices/{invoice_no}/status?token={API_TOKEN}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            status_map = {
                1: "🕓 Ожидает оплату",
                2: "⌛ Просрочен",
                3: "✅ Оплачен",
                4: "💰 Оплачен частично",
                5: "❌ Отменен",
                6: "💳 Оплачен банковской картой",
                7: "↩️ Платеж возвращен"
            }
            status = data.get("Status", "неизвестно")
            return f"📄 Статус счёта №{invoice_no}: {status_map.get(status, 'Неизвестный статус')}"
        else:
            return f"❌ Ошибка при получении статуса.\nКод: {response.status_code}\nТекст: {response.text}"
    except Exception as e:
        return f"⚠️ Ошибка при получении статуса: {e}"

# --- ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Выставить счёт")],
        [KeyboardButton("Статус счёта")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👋 Привет! Выберите действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "Выставить счёт":
        await update.message.reply_text("Введите сумму счёта (в BYN):")
        context.user_data["awaiting_amount"] = True
    elif context.user_data.get("awaiting_amount"):
        context.user_data["awaiting_amount"] = False
        result = create_invoice(text)
        await update.message.reply_text(result)
    elif text == "Статус счёта":
        await update.message.reply_text("Введите номер счёта (InvoiceNo):")
        context.user_data["awaiting_invoice"] = True
    elif context.user_data.get("awaiting_invoice"):
        context.user_data["awaiting_invoice"] = False
        result = get_invoice_status(text)
        await update.message.reply_text(result)
    else:
        await update.message.reply_text("Выберите действие с кнопок меню.")

# --- ЗАПУСК БОТА ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск webhook — идеально для Render
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
