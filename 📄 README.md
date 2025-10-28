# ExpressPay Telegram Bot

Телеграм-бот для выставления и проверки счетов через API ExpressPay.

## 🚀 Функционал
- Выставление счёта (`POST /v1/invoices`)
- Проверка статуса счёта (`GET /v1/invoices/{InvoiceNo}/status`)

## 🧰 Технологии
- Python 3.11+
- python-telegram-bot
- requests

## ▶️ Запуск локально
1. Установи зависимости:
   ```bash
   pip install -r requirements.txt
