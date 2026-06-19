FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Создаем директорию для данных
RUN mkdir -p /app/data && chmod 777 /app/data

# Устанавливаем переменные окружения
ENV DATA_DIR=/app/data
ENV PYTHONPATH=/app

# Запускаем правильный файл бота
CMD ["python", "discord_telegram_bot_advanced.py"]
