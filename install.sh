#!/bin/bash

# Installation Script for Discord-Telegram Bot
# For Linux Hosting

echo "🔧 Установка Discord-Telegram бота..."

# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Python и pip
sudo apt install python3 python3-pip python3-venv -y

# Создаем директорию для бота
mkdir -p /opt/discord-telegram-bot
cd /opt/discord-telegram-bot

# Клонируем репозиторий
git clone https://github.com/ttwintypink/discord-telegram-bridge.git .

# Делаем скрипты исполняемыми
chmod +x start_bot.sh
chmod +x install.sh

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt

# Создаем .env файл из примера
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️  Пожалуйста, отредактируйте .env файл с вашими токенами!"
fi

# Настраиваем systemd сервис
sudo cp discord-telegram-bot.service /etc/systemd/system/
sudo sed -i "s/your_username/$(whoami)/g" /etc/systemd/system/discord-telegram-bot.service
sudo sed -i "s|/path/to/your/project|/opt/discord-telegram-bot|g" /etc/systemd/system/discord-telegram-bot.service

# Перезагружаем systemd и включаем сервис
sudo systemctl daemon-reload
sudo systemctl enable discord-telegram-bot.service

echo "✅ Установка завершена!"
echo "📝 Пожалуйста, отредактируйте /opt/discord-telegram-bot/.env файл"
echo "🚀 Запуск: sudo systemctl start discord-telegram-bot"
echo "📊 Статус: sudo systemctl status discord-telegram-bot"
echo "📋 Логи: sudo journalctl -u discord-telegram-bot -f"
