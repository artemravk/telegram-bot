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
ACCOUNT_FILE = "account_no.txt"


# === Главное меню ===
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выставить счёт", callback_data="create_invoice")],
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")]
    ])


# === Функции для управления AccountNo ===
def get_next_account_no():
    """Генерирует следующий AccountNo (например, 301025001, 301025002 и т.д.)"""
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


# === Обработка нажатий кнопок ===
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


# === Получение детальной информации о счёте ===
def get_invoice_details(invoice_no: int):
    """Возвращает подробную информацию по номеру счёта (InvoiceNo)."""
    url = f"{API_URL}/{invoice_no}?token={EXPRESS_PAY_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


# === Получение списка счетов по AccountNo ===
def get_invoice_list(token: str, account_no: str):
    """Получает список счетов по AccountNo (без подписи)."""
    from_date = (datetime.now() - timedelta(days=60)).strftime("%d.%m.%Y")
    url = f"{API_URL}?Token={token}&AccountNo={account_no}&From={from_date}"

    response = requests.get(url)
    raw_text = response.text  # Сырой ответ API

    try:
        data = response.json()
    except Exception:
        data = {"error": f"Некорректный JSON: {raw_text}"}

    return data, raw_text


# === Обработка сообщений пользователя ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        # Создание счёта
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
                await update.message.reply_text(
                    f"✅ Счёт выставлен, но не удалось получить детали.\n"
                    f"InvoiceNo: {invoice_no}",
                    reply_markup=main_menu()
                )
        else:
            await update.message.reply_text(
                f"❌ Ошибка при выставлении счёта:\n{response.text}",
                reply_markup=main_menu()
            )

        context.user_data.clear()

    elif action == "check_status":
        # Проверка статуса счёта
        account_display = update.message.text.strip()

        # Извлекаем чистый AccountNo из формата 35077-1-301025001
        if "-" in account_display:
            account_no = account_display.split("-")[-1].strip()
        else:
            account_no = account_display.strip()

        data, raw = get_invoice_list(EXPRESS_PAY_TOKEN, account_no)

        # 👇 Отправляем сырое тело ответа для диагностики
        await update.message.reply_text(
            f"🧾 *Ответ ExpressPay (сырой)*:\n```\n{raw[:3000]}\n```",
            parse_mode="Markdown"
        )

        # Проверяем, что пришло от API
        if not isinstance(data, dict):
            await update.message.reply_text(
                f"❌ Некорректный ответ от ExpressPay:\n{data}",
                reply_markup=main_menu()
            )
            return

        if "error" in data:
            await update.message.reply_text(
                f"❌ Ошибка при получении статуса:\n{data['error']}",
                reply_markup=main_menu()
            )
            return

        invoices = data.get("Invoices") or data
        if not invoices or (isinstance(invoices, list) and len(invoices) == 0):
            await update.message.reply_text(
                f"❌ Счёт `{account_display}` не найден в системе ExpressPay.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
            return

        invoice = invoices[0] if isinstance(invoices, list) else invoices
        status = int(invoice.get("Status", 0))
        amount = invoice.get("Amount", "—")
        date = invoice.get("DateCreated", "—")

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
            f"📊 *Статус счёта*\n\n"
            f"Номер: `{account_display}`\n"
            f"Статус: *{statuses.get(status, 'Неизвестен')}*\n"
            f"Сумма: {amount} BYN\n"
            f"Дата выставления: {date}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

        context.user_data.clear()

    else:
        await update.message.reply_text("Выберите действие:", reply_markup=main_menu())


# === Основная функция ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 8443))

    # Запуск webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"{APP_URL}/{BOT_TOKEN}"
    )


if __name__ == "__main__":
    main()
