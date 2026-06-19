#!/bin/bash

# Discord-Telegram Bot Startup Script
# For Linux Hosting

echo "🚀 Запуск Discord-Telegram бота..."

# Переходим в директорию бота
cd "$(dirname "$0")"

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Пожалуйста, установите Python3."
    exit 1
fi

# Проверяем наличие pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не найден. Пожалуйста, установите pip3."
    exit 1
fi

# Устанавливаем зависимости если нужно
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение
source venv/bin/activate

# Устанавливаем зависимости
echo "📦 Установка зависимостей..."
pip install -r requirements.txt

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден. Пожалуйста, создайте его на основе .env.example"
    exit 1
fi

# Запускаем бота
echo "🤖 Запуск бота..."
python3 discord_telegram_bot_advanced.py
