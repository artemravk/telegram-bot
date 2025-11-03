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
        [InlineKeyboardButton("📊 Статус счёта", callback_data="check_status")],
        [InlineKeyboardButton("📅 Получить сумму оплат", callback_data="get_payments_menu")]  # ✅ новое название
    ])


# === Подменю выбора периода оплат ===
def payments_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 За сегодня", callback_data="payments_today")],
        [InlineKeyboardButton("📅 За вчера", callback_data="payments_yesterday")],
        [InlineKeyboardButton("🗓 За последние 3 дня", callback_data="payments_last3")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ])


# === Получение суммы оплат ===
def get_payments_sum(token: str, date_from: str, date_to: str):
    url = "https://api.express-pay.by/v1/payments"
    params = {
        "token": token,
        "From": date_from,
        "To": date_to
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None, f"Ошибка {response.status_code}: {response.text}"

    try:
        data = response.json()
    except Exception:
        return None, "Некорректный ответ от ExpressPay (не JSON)."

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

    elif query.data == "get_payments_menu":
        await query.message.reply_text("Выберите период:", reply_markup=payments_menu())

    elif query.data.startswith("payments_"):
        now = datetime.now()
        if query.data == "payments_today":
            date_from = now.strftime("%Y%m%d")
            date_to = now.strftime("%Y%m%d")
            period_text = "сегодня"

        elif query.data == "payments_yesterday":
            yesterday = now - timedelta(days=1)
            date_from = date_to = yesterday.strftime("%Y%m%d")
            period_text = "вчера"

        elif query.data == "payments_last3":
            date_to = (now - timedelta(days=1)).strftime("%Y%m%d")
            date_from = (now - timedelta(days=3)).strftime("%Y%m%d")
            period_text = "за последние три дня (без учёта сегодня)"

        await query.message.reply_text(f"⏳ Получаю данные об оплатах {period_text}...")

        total, error = get_payments_sum(EXPRESS_PAY_TOKEN, date_from, date_to)
        if error:
            await query.message.reply_text(f"❌ Ошибка: {error}", reply_markup=main_menu())
        else:
            await query.message.reply_text(
                f"📅 Общая сумма оплат {period_text}: *{total:.2f} BYN*",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )


# === Получение деталей счёта ===
def get_invoice_details(invoice_no: int):
    url = f"{API_URL}/{invoice_no}?token={EXPRESS_PAY_TOKEN}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


# === Получение списка счетов по AccountNo ===
def get_invoice_list(token: str, account_no: str):
    params = {"Token": token, "AccountNo": account_no}
    response = requests.get(API_URL, params=params)
    try:
        return response.json()
    except Exception:
        return {"Error": {"Msg": "Некорректный ответ от ExpressPay"}}


# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")

    if action == "create_invoice":
        amount = update.message.text.strip().replace(",", ".")
        account_no = datetime.now().strftime("%d%m%y%H%M%S")

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
                    f"✅ Счёт выставлен, но не удалось получить детали.\nInvoiceNo: {invoice_no}",
                    reply_markup=main_menu()
                )
        else:
            await update.message.reply_text(
                f"❌ Ошибка при выставлении счёта:\n{response.text}",
                reply_markup=main_menu()
            )
        context.user_data.clear()

    elif action == "check_status":
        account_display = update.message.text.strip()
        account_no = account_display.split("-")[-1] if "-" in account_display else account_display

        data = get_invoice_list(EXPRESS_PAY_TOKEN, account_no)
        if "Error" in data:
            await update.message.reply_text(
                f"❌ Ошибка от ExpressPay:\n{data['Error']['Msg']}",
                reply_markup=main_menu()
            )
            return

        items = data.get("Items", [])
        if not items:
            await update.message.reply_text(
                f"❌ Счёт `{account_display}` не найден.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
            return

        invoice = items[-1]
        status = int(invoice.get("Status", 0))
        amount = invoice.get("Amount", "—")
        created_raw = invoice.get("Created", "")
        date = (
            datetime.strptime(created_raw, "%Y%m%d%H%M%S").strftime("%d.%m.%Y %H:%M")
            if created_raw else "—"
        )

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


# === Запуск ===
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
