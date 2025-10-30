    # === ПРОВЕРКА СТАТУСА ПО ACCOUNTNO ===
    elif action == "check_status":
        account_display = update.message.text.strip()

        # Извлекаем внутренний AccountNo (после "35077-1-")
        if "-" in account_display:
            account_no = account_display.split("-")[-1]
        else:
            account_no = account_display

        url = f"{API_URL}?token={EXPRESS_PAY_TOKEN}&AccountNo={account_no}"
        response = requests.get(url)

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                await update.message.reply_text(
                    f"❌ Некорректный ответ от API:\n{response.text}",
                    reply_markup=main_menu()
                )
                context.user_data.clear()
                return

            # Если API вернул пустой список
            if not data:
                await update.message.reply_text(
                    f"❌ Счёт с номером `{account_display}` не найден.",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
            else:
                invoice = data[0]
                status = invoice.get("Status")
                statuses = {
                    1: "Ожидает оплату",
                    2: "Просрочен",
                    3: "Оплачен",
                    4: "Оплачен частично",
                    5: "Отменен",
                    6: "Оплачен картой",
                    7: "Платёж возвращен"
                }

                amount = invoice.get("Amount", "—")
                date = invoice.get("DateCreated", "—")

                await update.message.reply_text(
                    f"📊 *Статус счёта*\n\n"
                    f"Номер: `{account_display}`\n"
                    f"Статус: *{statuses.get(status, 'Неизвестен')}*\n"
                    f"Сумма: {amount} BYN\n"
                    f"Дата выставления: {date}",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )

        else:
            await update.message.reply_text(
                f"❌ Ошибка при получении статуса:\n{response.text}",
                reply_markup=main_menu()
            )

        context.user_data.clear()
