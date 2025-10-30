import os
import hmac
import hashlib
import json
import requests
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# === Настройки ===
EXPRESS_PAY_TOKEN = os.getenv("EXPRESS_PAY_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
SECRET_WORD = os.getenv("SECRET_WORD", "")  # для проверки подписи ExpressPay
API_URL = "https://api.express-pay.by/v1/invoices"
ACCOUNT_FILE = "account_no.txt"

# === Главное меню ===
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")]
    ])

# === Счётчик номеров AccountNo ===
def get_next_account_no():
    today = datetime.now().strftime("%d%m%y")
    if os.path.exists(ACCOUNT_FILE):
        with open(ACCOUNT_FILE, "r") as f:
            data = f.read().strip()
    else:
        data = ""

    if not data.startswith(today):
        next_no = 1
    else:
        last_no = int(data[6:])
        next_no = last_no + 1

    new_account_no = f"{today}{next_no:03d}"
    with open(ACCOUNT_FILE, "w") as f:
        f.write(new_account_no)
    return new_account_no

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите действие:", reply_markup=main_menu())

# === Кнопки ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        await query.message.reply_text("Выберите действие:", reply_markup=main_menu())
    elif query.data == "create_invoice":
        await query.message.reply_text("Введите сумму счёта (например: 25,50):")
        context.user_data["action"] = "create_invoice"
    elif query.data == "check_status":
        await query.message.reply_text("Введите номер счёта в формате 35077-1-XXXXXX:")
        context.user_data["action"] = "check_status"

# === Детали счёта ===
def get_invoice_details(invoice_no: int):
    url = f"{API_URL}/{invoice_no}?token={EXPRESS_PAY_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        amount = update.message.text.strip().replace(",", ".")
        account_no = get_next_account_no()
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
            details = get_invoice_details(invoice_no)
            if details:
                amount_info = details.get("Amount")
                account_info = details.get("AccountNo")
                account_display = f"35077-1-{account_info}"
                await update.message.reply_text(
                    f"✅ Счёт на {amount_info} рублей выставлен.\n"
                    f"Номер счёта: `{account_display}`",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
        else:
            await update.message.reply_text(f"❌ Ошибка:\n{response.text}", reply_markup=main_menu())
        context.user_data.clear()

    elif action == "check_status":
        acc_input = update.message.text.strip()
        if acc_input.startswith("35077-1-"):
            acc_no = acc_input.split("-1-")[1]
        else:
            acc_no = acc_input

        url = f"{API_URL}?token={EXPRESS_PAY_TOKEN}&AccountNo={acc_no}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json().get("Items", [])
            if not data:
                await update.message.reply_text("❌ Счёт не найден.", reply_markup=main_menu())
                return
            invoice = data[-1]
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
                f"📊 Статус счёта\n\n"
                f"Номер: `35077-1-{acc_no}`\n"
                f"Статус: {statuses.get(invoice.get('Status'), 'Неизвестен')}\n"
                f"Сумма: {invoice.get('Amount')} BYN\n"
                f"Дата выставления: {invoice.get('Created')}",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text(f"❌ Ошибка:\n{response.text}", reply_markup=main_menu())
        context.user_data.clear()

# === Проверка подписи ExpressPay ===
def verify_signature(data: str, signature: str) -> bool:
    expected = hmac.new(SECRET_WORD.encode(), data.encode(), hashlib.sha1).hexdigest().upper()
    return hmac.compare_digest(signature.upper(), expected)

# === Обработка уведомлений от ExpressPay ===
async def expresspay_notification(request):
    try:
        data = request.post()
        data = await data
        json_data = data.get("Data")
        signature = data.get("Signature", "")

        if not json_data:
            return web.Response(text="Missing Data", status=400)

        if SECRET_WORD:
            if not verify_signature(json_data, signature):
                return web.Response(text="Invalid signature", status=403)

        payment = json.loads(json_data)
        print("✅ Поступило уведомление о платеже:", payment)

        return web.Response(text="OK", status=200)

    except Exception as e:
        print("❌ Ошибка при обработке уведомления:", e)
        return web.Response(text="Error", status=500)

# === Основная функция ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # === aiohttp web app для уведомлений ===
    web_app = web.Application()
    web_app.router.add_post("/expresspay_notify", expresspay_notification)

    # Telegram webhook
    port = int(os.environ.get("PORT", 8443))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}",
    )

    # ExpressPay webhook
    web.run_app(web_app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
