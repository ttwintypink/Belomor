import requests
from requests.exceptions import SSLError, Timeout, RequestException
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
import json
import time
import threading

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscordTelegramBot:
    def load_config(self):
        """Загружает конфигурацию из config.json"""
        try:
            # Определяем путь к config.json относительно расположения скрипта
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, 'config.json')
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Конфигурация успешно загружена из {config_path}")
                return config
        except FileNotFoundError:
            logger.error(f"Файл config.json не найден по пути: {config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга config.json: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            raise
    
    def __init__(self):
        # Загрузка конфигурации
        self.config = self.load_config()
        
        # Discord настройки из config.json
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_SERVER_ID = self.config['discord']['server_id']
        self.DISCORD_CHANNEL_ID = self.config['discord']['channel_id']
        self.DISCORD_SERVER_NAME = self.config['discord']['server_name']
        
        # Telegram настройки из config.json
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.ADMIN_ID = self.config['telegram']['admin_id']
        
        # Настройки мониторинга из config.json
        self.polling_interval = self.config['monitoring']['polling_interval']
        self.message_limit = self.config['monitoring']['message_limit']
        
        # Настройки производительности из config.json
        self.batch_size = self.config['performance']['batch_size']
        self.batch_delay = self.config['performance']['batch_delay']
        self.max_concurrent_sends = self.config['performance']['max_concurrent_sends']
        
        # Настройки функций из config.json
        self.mute_enabled = self.config['features']['mute_enabled']
        self.default_mute_duration = self.config['features']['default_mute_duration']
        self.subscriptions_enabled = self.config['features']['subscriptions_enabled']
        self.attachments_enabled = self.config['features']['attachments_enabled']
        self.auto_delete_enabled = self.config['features']['auto_delete_enabled']
        self.auto_delete_hours = self.config['features']['auto_delete_hours']
        
        # Discord API заголовки с оптимизацией соединения
        self.headers = {
            'Authorization': f'{self.DISCORD_TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Connection': 'keep-alive'
        }
        
        # Хранилище подписчиков и сообщений
        self.subscribers = set()  # ID пользователей, которые подписаны
        self.user_messages = {}  # ID пользователя -> ID сообщения для редактирования
        self.muted_users = {}  # Хранит {user_id: mute_end_time}
        self.last_message_id = None
        self.start_time = time.time()
        self.message_count = 0
        
        # Хранилище отправленных сообщений для автоудаления
        self.sent_messages = {}  # {(chat_id, message_id): timestamp}
        
        # Semaphore для ограничения параллельных отправок
        self.send_semaphore = asyncio.Semaphore(self.max_concurrent_sends)
        
        # Файл для сохранения подписчиков
        self.subscribers_file = "subscribers.json"
        self.load_subscribers()
        
        # Ссылка на приложение Telegram для отправки сообщений
        self.telegram_app = None
    
    def load_subscribers(self):
        """Загружает список подписчиков из файла с оптимизацией для больших файлов"""
        try:
            if os.path.exists(self.subscribers_file):
                with open(self.subscribers_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    subscribers_list = data.get('subscribers', [])
                    self.subscribers = set(subscribers_list)  # Используем set для быстрого поиска
                logger.info(f"Загружено {len(self.subscribers)} подписчиков")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга файла подписчиков: {e}")
            self.subscribers = set()  # Создаем пустой набор при ошибке
        except Exception as e:
            logger.error(f"Ошибка загрузки подписчиков: {e}")
            self.subscribers = set()
    
    def save_subscribers(self):
        """Сохраняет список подписчиков в файл с оптимизацией"""
        try:
            with open(self.subscribers_file, 'w', encoding='utf-8') as f:
                json.dump({'subscribers': list(self.subscribers)}, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения подписчиков: {e}")
    
    def get_discord_messages(self):
        """Получает последние сообщения из Discord канала с retry механизмом"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                url = f"https://discord.com/api/v9/channels/{self.DISCORD_CHANNEL_ID}/messages?limit={self.message_limit}"
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code == 200:
                    messages = response.json()
                    logger.debug(f"Получено {len(messages)} сообщений из Discord")
                    return messages
                else:
                    logger.error(f"Ошибка Discord API: {response.status_code} - {response.text}")
                    return []
            except SSLError as e:
                logger.warning(f"SSL ошибка (попытка {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error("Не удалось преодолеть SSL ошибку после всех попыток")
                    return []
            except Timeout:
                logger.warning(f"Таймаут при запросе к Discord API (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error("Таймаут после всех попыток")
                    return []
            except RequestException as e:
                logger.error(f"Ошибка запроса к Discord API: {e}")
                return []
            except Exception as e:
                logger.error(f"Неожиданная ошибка при получении сообщений из Discord: {e}")
                return []
        
        return []
    
    async def forward_to_telegram(self, message, user_id=None):
        """Отправляет сообщение в Telegram всем подписчикам или конкретному пользователю"""
        try:
            # Получаем время сообщения в МСК (UTC+3)
            timestamp = message.get('timestamp', '')
            utc_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            msk_timezone = timezone(timedelta(hours=3))
            msk_time = utc_time.astimezone(msk_timezone).strftime("%H:%M:%S %d.%m.%Y")
            
            # Получаем информацию об авторе (используем ник с сервера)
            author = message.get('author', {})
            author_name = author.get('username', 'Unknown')
            # Пытаемся получить ник с сервера (server-specific nickname)
            member_data = message.get('member', {})
            server_nick = member_data.get('nick')
            # Приоритет: серверный ник > global_name > username
            author_display_name = server_nick if server_nick else author.get('global_name', author_name)
            
            # Получаем контент сообщения и убираем пинги ролей
            content = message.get('content', '')
            # Убираем пинги ролей (@role)
            import re
            content = re.sub(r'<@&\d+>', '', content)
            # Убираем символ '>' в начале сообщения
            content = content.lstrip('>')
            # Убираем двойные кавычки в конце, если они есть
            if content.endswith('""'):
                content = content[:-2]
            # Убираем лишние пробелы после удаления пингов
            content = content.strip()
            
            # Формируем красивое сообщение для Telegram с HTML форматированием
            telegram_message = f"""
<b>📨 Новое сообщение из Discord</b>

<b>👤 Автор:</b> <i>{author_display_name} (@{author_name})</i>
<b>⏰ Время отправки сообщения Discord:</b> <i>{msk_time} (МСК)</i>

<b>💬 Сообщение:</b>
{content}
            """
            
            # Добавляем информацию о вложениях (если включено в config)
            if self.attachments_enabled:
                attachments = message.get('attachments', [])
                if attachments:
                    telegram_message += "\n\n<b>📎 Вложения:</b>\n"
                    for attachment in attachments:
                        telegram_message += f"• {attachment.get('url', 'No URL')}\n"
            
            # Определяем, кому отправлять
            recipients = [user_id] if user_id else [uid for uid in self.subscribers if uid not in self.muted_users or self.muted_users[uid] < time.time()]
            
            # Отправляем сообщение всем получателям одновременно для скорости
            if recipients:
                # Батчинг: разбиваем на группы для избежания rate limiting
                for i in range(0, len(recipients), self.batch_size):
                    batch = recipients[i:i + self.batch_size]
                    send_tasks = []
                    for recipient_id in batch:
                        if self.telegram_app:
                            send_tasks.append(self._send_to_user(recipient_id, telegram_message))
                    
                    # Выполняем отправки батча параллельно
                    await asyncio.gather(*send_tasks, return_exceptions=True)
                    
                    # Небольшая пауза между батчами для избежания rate limiting
                    if i + self.batch_size < len(recipients):
                        await asyncio.sleep(self.batch_delay)
            
            # Увеличиваем счетчик сообщений
            self.message_count += 1
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения в Telegram: {e}")
    
    async def _send_to_user(self, user_id, message):
        """Вспомогательный метод для отправки сообщения конкретному пользователю с улучшенной обработкой ошибок"""
        async with self.send_semaphore:  # Ограничение параллельных отправок
            try:
                sent_message = await self.telegram_app.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML',
                    read_timeout=10,
                    write_timeout=10,
                    connect_timeout=10
                )
                # Сохраняем ID сообщения для автоудаления (если включено)
                if self.auto_delete_enabled:
                    self.sent_messages[(user_id, sent_message.message_id)] = time.time()
                return sent_message.message_id
            except Exception as e:
                # Изолируем ошибки - не прерываем отправку другим пользователям
                logger.debug(f"Ошибка отправки пользователю {user_id}: {e}")
                return None
    
    async def cleanup_old_messages(self):
        """Удаляет сообщения старше указанного времени"""
        if not self.auto_delete_enabled or not self.telegram_app:
            return
        
        current_time = time.time()
        delete_threshold = self.auto_delete_hours * 3600  # Конвертируем часы в секунды
        
        messages_to_delete = []
        for (chat_id, message_id), sent_time in list(self.sent_messages.items()):
            if current_time - sent_time > delete_threshold:
                messages_to_delete.append((chat_id, message_id))
        
        if messages_to_delete:
            logger.info(f"Найдено {len(messages_to_delete)} сообщений для удаления")
            for chat_id, message_id in messages_to_delete:
                try:
                    await self.telegram_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    del self.sent_messages[(chat_id, message_id)]
                    logger.debug(f"Удалено сообщение {message_id} для пользователя {chat_id}")
                except Exception as e:
                    logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
                    # Удаляем из словаря даже при ошибке, чтобы не пытаться снова
                    if (chat_id, message_id) in self.sent_messages:
                        del self.sent_messages[(chat_id, message_id)]
    
    async def cleanup_chat_before_pinned(self, user_id):
        """Удаляет все сообщения до закрепленного сообщения для конкретного пользователя"""
        try:
            # Получаем историю чата
            messages = []
            async for message in self.telegram_app.bot.get_chat_history(chat_id=user_id, limit=100):
                messages.append(message)
            
            # Ищем закрепленное сообщение
            pinned_message_id = None
            for message in messages:
                if message.pinned and "Вы подписаны на уведомления" in message.text:
                    pinned_message_id = message.message_id
                    break
            
            if not pinned_message_id:
                logger.debug(f"Не найдено закрепленное сообщение для пользователя {user_id}")
                return
            
            # Удаляем все сообщения до закрепленного (кроме самого закрепленного)
            messages_to_delete = []
            found_pinned = False
            for message in messages:
                if message.message_id == pinned_message_id:
                    found_pinned = True
                    continue
                if found_pinned and not message.pinned:
                    messages_to_delete.append(message.message_id)
            
            if messages_to_delete:
                logger.info(f"Удаление {len(messages_to_delete)} сообщений до закрепленного для пользователя {user_id}")
                for message_id in messages_to_delete:
                    try:
                        await self.telegram_app.bot.delete_message(chat_id=user_id, message_id=message_id)
                    except Exception as e:
                        logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
                        
        except Exception as e:
            logger.error(f"Ошибка при очистке чата пользователя {user_id}: {e}")
    
    async def cleanup_loop(self):
        """Фоновый цикл для периодического удаления старых сообщений и очистки чатов"""
        while True:
            try:
                await asyncio.sleep(3600)  # Проверка каждый час
                await self.cleanup_old_messages()
                
                # Очистка чатов до закрепленных сообщений (каждые 6 часов)
                current_hour = datetime.now().hour
                if current_hour % 6 == 0:  # Каждые 6 часов (0, 6, 12, 18)
                    logger.info("Запуск очистки чатов до закрепленных сообщений")
                    for user_id in self.user_messages.keys():
                        await self.cleanup_chat_before_pinned(user_id)
                        
            except asyncio.CancelledError:
                logger.info("Цикл автоудаления остановлен")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле автоудаления: {e}")
                await asyncio.sleep(300)  # Пауза 5 минут при ошибке
    
    def start_cleanup_sync(self):
        """Запускает цикл автоудаления в синхронном режиме"""
        logger.info(f"Запуск цикла автоудаления сообщений (каждые {self.auto_delete_hours} часов)")
        while True:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.cleanup_old_messages())
                loop.close()
                time.sleep(3600)  # Проверка каждый час
            except Exception as e:
                logger.error(f"Ошибка в синхронном цикле автоудаления: {e}")
                time.sleep(300)
    
    async def check_new_messages(self):
        """Проверяет новые сообщения и пересылает их"""
        messages = self.get_discord_messages()
        
        if not messages:
            return
        
        # Сортируем сообщения по времени (новые первые)
        messages.sort(key=lambda x: x.get('id', '0'), reverse=True)
        
        # Если это первый запуск, устанавливаем последнее сообщение
        if self.last_message_id is None:
            self.last_message_id = messages[0].get('id') if messages else None
            logger.info(f"Первый запуск, установлено last_message_id: {self.last_message_id}")
            return
        
        # Ищем новые сообщения
        new_messages = []
        for message in messages:
            message_id = message.get('id')
            if message_id and int(message_id) > int(self.last_message_id):
                new_messages.append(message)
        
        if new_messages:
            logger.info(f"Найдено {len(new_messages)} новых сообщений")
            # Пересылаем новые сообщения в обратном порядке (старые → новые)
            for message in reversed(new_messages):
                await self.forward_to_telegram(message)
            
            # Обновляем ID последнего сообщения
            self.last_message_id = new_messages[-1].get('id')
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start - моментальная подписка"""
        # Проверяем, включена ли функция подписок
        if not self.subscriptions_enabled:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="🚫 Функция подписок отключена администратором."
            )
            return
        
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получена команда /start от пользователя {user_id} ({user_name})")
        
        try:
            # Удаляем команду /start
            await update.message.delete()
            
            # Проверяем, есть ли уже закрепленное сообщение от этого пользователя
            if user_id in self.user_messages:
                logger.info(f"Пользователь {user_id} уже использует бота")
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ Вы уже подписаны на уведомления!"
                )
                return
            
            # Моментально подписываем пользователя
            self.subscribers.add(user_id)
            self.save_subscribers()
            
            # Создаем кнопку отписки
            keyboard = [[InlineKeyboardButton("🔕 Отписаться", callback_data="unsubscribe")]]
            text = f"🔔 Вы подписаны на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'\n\n🤖 Бот готов к работе!"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение и закрепляем его
            sent_message = await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup
            )
            
            # Закрепляем сообщение
            await context.bot.pin_chat_message(
                chat_id=user_id,
                message_id=sent_message.message_id
            )
            
            # Сохраняем ID сообщения для будущего редактирования и удаления
            self.user_messages[user_id] = sent_message.message_id
            if self.auto_delete_enabled:
                self.sent_messages[(user_id, sent_message.message_id)] = time.time()
            
            logger.info(f"Пользователь {user_id} подписался на уведомления через /start")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /start: {e}")
    
    async def clean_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clean - очистка чата до закрепленного сообщения"""
        user_id = update.effective_user.id
        
        try:
            await update.message.delete()
            await self.cleanup_chat_before_pinned(user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Чат очищен до закрепленного сообщения!"
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении /clean: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ошибка при очистке чата"
            )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status - статистика бота"""
        user_id = update.effective_user.id
        
        try:
            uptime = time.time() - self.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            
            status_text = f"""
📊 <b>Статистика бота</b>

👥 Подписчиков: <i>{len(self.subscribers)}</i>
📨 Переслано сообщений: <i>{self.message_count}</i>
⏱️ Время работы: <i>{uptime_hours}ч {uptime_minutes}м</i>
🔔 Сервер: <i>{self.DISCORD_SERVER_NAME}</i>
⚡ Интервал проверки: <i>{self.polling_interval} сек</i>
            """
            
            await context.bot.send_message(
                chat_id=user_id,
                text=status_text,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении /status: {e}")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats (только для администратора)"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            logger.warning(f"Пользователь {user_id} ({user_name}) пытался получить доступ к /stats")
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        logger.info(f"Получена команда /stats от администратора {user_id} ({user_name})")
        
        try:
            # Удаляем команду /stats
            await update.message.delete()
            
            # Рассчитываем время работы
            uptime = time.time() - self.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            
            # Количество замьюченных пользователей
            muted_count = len([uid for uid, end_time in self.muted_users.items() if end_time > time.time()])
            
            # Формируем статистику
            stats_message = f"""
📊 Статистика бота

👥 Подписчики: {len(self.subscribers)}
🔇 Замьюченные: {muted_count}
📨 Сообщений переслано: {self.message_count}
⏰ Время работы: {uptime_hours}ч {uptime_minutes}м
📅 Запущен: {datetime.fromtimestamp(self.start_time).strftime('%d.%m.%Y %H:%M')}

Сервер Discord: {self.DISCORD_SERVER_NAME}
            """
            
            await context.bot.send_message(
                chat_id=user_id,
                text=stats_message
            )
            
            logger.info(f"Отправлена статистика администратору {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /stats: {e}")
    
    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /mute"""
        # Проверяем, включена ли функция мьюта
        if not self.mute_enabled:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="🚫 Функция мьюта отключена администратором."
            )
            return
        
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получена команда /mute от пользователя {user_id} ({user_name})")
        
        try:
            # Удаляем команду /mute
            await update.message.delete()
            
            # По умолчанию мьют из config.json
            mute_duration = self.default_mute_duration
            
            # Проверяем аргументы
            if context.args:
                arg = context.args[0].lower()
                if arg == '1h' or arg == 'час':
                    mute_duration = 3600
                elif arg == '6h' or arg == '6час':
                    mute_duration = 21600
                elif arg == '12h' or arg == '12час':
                    mute_duration = 43200
                elif arg == '1d' or arg == 'день':
                    mute_duration = 86400
                else:
                    mute_duration = 3600  # по умолчанию
            
            # Устанавливаем мьют
            mute_end_time = time.time() + mute_duration
            self.muted_users[user_id] = mute_end_time
            
            # Формируем время окончания
            end_time_str = datetime.fromtimestamp(mute_end_time).strftime('%d.%m.%Y %H:%M')
            
            mute_message = f"""
🔇 Уведомления отключены

⏰ До: {end_time_str}
📅 Длительность: {mute_duration // 3600}ч

Чтобы включить раньше: /unmute
            """
            
            await context.bot.send_message(
                chat_id=user_id,
                text=mute_message
            )
            
            logger.info(f"Пользователь {user_id} замьючен на {mute_duration // 3600} часов")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /mute: {e}")
    
    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /unmute"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получена команда /unmute от пользователя {user_id} ({user_name})")
        
        try:
            # Удаляем команду /unmute
            await update.message.delete()
            
            # Проверяем, замьючен ли пользователь
            if user_id in self.muted_users and self.muted_users[user_id] > time.time():
                # Убираем мьют
                del self.muted_users[user_id]
                
                unmute_message = """
🔔 Уведомления включены

Теперь вы будете получать сообщения из Discord снова!
                """
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=unmute_message
                )
                
                logger.info(f"Пользователь {user_id} размьючен")
            else:
                # Пользователь не замьючен
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🔔 У вас и так включены уведомления!"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обработке /unmute: {e}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на инлайн кнопки"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        await query.answer()  # Показываем "загрузку" на кнопке
        
        logger.info(f"Нажата кнопка {query.data} пользователем {user_id}")
        
        try:
            if query.data == "subscribe":
                # Подписка (этот кейс не должен вызываться, но оставим для надежности)
                self.subscribers.add(user_id)
                self.save_subscribers()
                
                # Редактируем сообщение
                keyboard = [[InlineKeyboardButton("🔕 Отписаться", callback_data="unsubscribe")]]
                text = f"🔔 Вы успешно подписались на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
                
                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Пользователь {user_id} подписался на уведомления")
                
                # Отправляем последние 3 сообщения из Discord для новеньких (только если есть новые)
                # await self.send_recent_messages(user_id)  # Закомментировано, чтобы не спамить старыми сообщениями
                
            elif query.data == "unsubscribe":
                # Отписка
                self.subscribers.discard(user_id)
                self.save_subscribers()
                
                # Редактируем сообщение
                keyboard = [[InlineKeyboardButton("🔔 Подписаться", callback_data="subscribe")]]
                text = f"🔕 Вы успешно отписались от уведомлений от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
                
                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Пользователь {user_id} отписался от уведомлений")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки: {e}")
    
    async def handle_all_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик всех сообщений кроме команд"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получено сообщение от пользователя {user_id} ({user_name})")
        
        try:
            # Удаляем сообщение пользователя
            await update.message.delete()
            
            error_message = "Я бот для уведомлений. Отправлять мне сообщения нельзя. \nИспользуйте команду /start для управления подпиской."
            
            await context.bot.send_message(
                chat_id=user_id,
                text=error_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Отправлено сообщение об ошибке пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
    
    async def send_recent_messages(self, user_id):
        """Отправляет последние 3 сообщения из Discord новому подписчику"""
        messages = self.get_discord_messages()
        
        if messages:
            # Берем последние 3 сообщения
            recent_messages = messages[:3]
            for message in reversed(recent_messages):  # В хронологическом порядке
                await self.forward_to_telegram(message, user_id)
    
    def start_monitoring_sync(self):
        """Запускает мониторинг канала в синхронном режиме"""
        logger.info("Запуск мониторинга Discord канала...")
        logger.info(f"Сервер: {self.DISCORD_SERVER_ID}")
        logger.info(f"Канал: {self.DISCORD_CHANNEL_ID}")
        logger.info(f"Подписчиков: {len(self.subscribers)}")
        logger.info(f"Интервал проверки: {self.polling_interval} сек")
        
        # Проверяем подключение к Discord
        test_messages = self.get_discord_messages()
        if test_messages is None:
            logger.error("Не удалось подключиться к Discord. Проверьте токен.")
            return
        
        logger.info("Успешное подключение к Discord API")
        
        # Основной цикл мониторинга
        while True:
            try:
                # Используем asyncio.run_coroutine_threadsafe для вызова async функции
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.check_new_messages())
                loop.close()
                
                time.sleep(self.polling_interval)
                
            except KeyboardInterrupt:
                logger.info("Мониторинг остановлен вручную")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(5)  # Пауза перед повторной попыткой

def main():
    # Создаем экземпляр бота
    bot = DiscordTelegramBot()
    
    # Создаем приложение Telegram
    application = Application.builder().token(bot.TELEGRAM_TOKEN).build()
    
    # Устанавливаем ссылку на приложение для отправки сообщений
    bot.telegram_app = application
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("stats", bot.stats_command))
    application.add_handler(CommandHandler("status", bot.status_command))
    application.add_handler(CommandHandler("clean", bot.clean_command))
    application.add_handler(CommandHandler("mute", bot.mute_command))
    application.add_handler(CommandHandler("unmute", bot.unmute_command))
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Добавляем обработчик для всех сообщений кроме команд
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_all_messages))
    
    # Запускаем мониторинг Discord в отдельном потоке
    monitor_thread = threading.Thread(target=bot.start_monitoring_sync, daemon=True)
    monitor_thread.start()
    
    # Запускаем автоудаление сообщений в отдельном потоке
    if bot.auto_delete_enabled:
        cleanup_thread = threading.Thread(target=bot.start_cleanup_sync, daemon=True)
        cleanup_thread.start()
        logger.info(f"Автоудаление сообщений включено (каждые {bot.auto_delete_hours} часов)")
    
    logger.info("Запуск Telegram бота...")
    
    try:
        # Запускаем Telegram бота
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except TimeoutError:
        logger.error("Таймаут операции. Перезапуск бота...")
        # При таймауте пытаемся перезапустить
        main()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        # При критической ошибке пытаемся перезапустить через 10 секунд
        logger.info("Попытка перезапуска через 10 секунд...")
        time.sleep(10)
        main()

if __name__ == "__main__":
    main()
