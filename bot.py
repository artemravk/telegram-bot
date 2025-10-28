import logging
import os
import requests
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === НАСТРОЙКИ ===
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
EXPRESSPAY_TOKEN = os.getenv("EXPRESSPAY_TOKEN")

if not TOKEN_TELEGRAM or not EXPRESSPAY_TOKEN:
    raise ValueError("Ошибка: переменные TOKEN_TELEGRAM и EXPRESSPAY_TOKEN не заданы.")

# === ЛОГГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ХРАНЕНИЕ СЧЕТОВ ===
user_invoices = {}

# === EXPRESSPAY API ===
def create_invoice(amount):
    """Создаёт новый счёт"""
    date_str = datetime.now().strftime("%d%m%y")
    account_no = f"{date_str}001"
    data = {
        "Token": EXPRESSPAY_TOKEN,
        "AccountNo": account_no,
        "Amount": f"{amount}",
        "Currency": 933,
        "Info": "организация доставки",
    }
    url = f"https://api.express-pay.by/v1/invoices?token={EXPRESSPAY_TOKEN}"
    response = requests.post(url, json=data)
    return response.json()

def get_invoice_status(invoice_no):
    """Проверяет статус счёта"""
    url = f"https://api.express-pay.by/v1/invoices/{invoice_no}/status?token={EXPRESSPAY_TOKEN}"
    response = requests.get(url)
    return response.json()

# === TELEGRAM ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("Выставить счёт"), KeyboardButton("Статус счёта")]]

