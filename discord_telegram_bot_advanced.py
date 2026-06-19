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

class BufferHandler(logging.Handler):
    """Кастомный логгер для записи в буфер"""
    def __init__(self, buffer):
        super().__init__()
        self.buffer = buffer
    
    def emit(self, record):
        log_entry = self.format(record)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.buffer.append(f"[{timestamp}] {log_entry}")
        # Храним только последние 1000 строк
        if len(self.buffer) > 1000:
            self.buffer.pop(0)

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
        
        # Хранение логов в памяти
        self.logs_buffer = []
        
        # Добавляем кастомный логгер для записи в буфер
        buffer_handler = BufferHandler(self.logs_buffer)
        buffer_handler.setLevel(logging.INFO)
        logger.addHandler(buffer_handler)
        
        # Discord настройки из config.json
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_SERVER_ID = self.config['discord']['server_id']
        self.DISCORD_CHANNEL_ID = self.config['discord']['channel_id']
        self.DISCORD_SERVER_NAME = self.config['discord']['server_name']
        
        # Telegram настройки из config.json
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.ADMIN_ID = int(self.config['telegram']['admin_id'])
        
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
        
        # Статистика активности подписчиков
        self.subscriber_activity = {}  # {user_id: {'subscribed_at': timestamp, 'messages_received': 0, 'last_activity': timestamp}}
        
        # Шаблоны рассылок
        self.broadcast_templates = {}  # {name: text}
        
        # Лог действий админа
        self.admin_log = []  # [{'timestamp': timestamp, 'action': str, 'details': str}]
        
        # Хранилище отправленных сообщений для автоудаления
        self.sent_messages = {}  # {(chat_id, message_id): timestamp}
        
        # Semaphore для ограничения параллельных отправок
        self.send_semaphore = asyncio.Semaphore(self.max_concurrent_sends)
        
        # Файл для сохранения подписчиков
        self.subscribers_file = "subscribers.json"
        self.load_subscribers()
        
        # Ссылка на приложение Telegram для отправки сообщений
        self.telegram_app = None
    
    def get_server_nickname(self, user_id):
        """Получает серверный никнейм пользователя через Discord API"""
        try:
            url = f"https://discord.com/api/v10/guilds/{self.DISCORD_SERVER_ID}/members/{user_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                member_data = response.json()
                server_nick = member_data.get('nick')
                logger.info(f"Получен серверный никнейм для {user_id}: {server_nick}")
                return server_nick
            else:
                logger.warning(f"Не удалось получить серверный никнейм для {user_id}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении серверного никнейма для {user_id}: {e}")
            return None
    
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
            author_id = author.get('id')
            
            # Для сервера 1506228881902801027 получаем серверный никнейм через API
            if self.DISCORD_SERVER_ID == '1506228881902801027' and author_id:
                server_nick = self.get_server_nickname(author_id)
                if server_nick:
                    author_display_name = server_nick
                    logger.info(f"Используем серверный никнейм: {server_nick}")
                else:
                    # Если не удалось получить серверный ник, используем global_name
                    author_display_name = author.get('global_name', author_name)
                    logger.info(f"Не удалось получить серверный ник, используем: {author_display_name}")
            else:
                # Для других серверов используем данные из сообщения
                member_data = message.get('member', {})
                server_nick = member_data.get('nick')
                author_display_name = server_nick if server_nick else author.get('global_name', author_name)
                logger.info(f"Используем: {author_display_name} (server_nick={server_nick}, global_name={author.get('global_name')}, username={author_name})")
            
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
<b> 📨 Новое сообщение из Discord </b>

<b> 👤 Автор: </b> <i>{author_display_name} (@{author_name})</i>
<b> ⏰ Время отправки сообщения Discord: </b> <i>{msk_time}</i>

<b> 💬 Сообщение: </b> 
<i>{content}</i>
            """
            
            # Добавляем информацию о вложениях (если включено в config)
            if self.attachments_enabled:
                attachments = message.get('attachments', [])
                if attachments:
                    telegram_message += "\n\n<b>\U0001F4CE Вложения:</b>\n"
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
            
            # Обновляем статистику активности получателей
            for recipient_id in recipients:
                if recipient_id in self.subscriber_activity:
                    self.subscriber_activity[recipient_id]['messages_received'] += 1
                    self.subscriber_activity[recipient_id]['last_activity'] = time.time()
            
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
                text="\U0001F6AB Функция подписок отключена администратором."
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
                    text="\U00002705 Вы уже подписаны на уведомления!"
                )
                return
            
            # Моментально подписываем пользователя
            self.subscribers.add(user_id)
            self.save_subscribers()
            
            # Записываем активность подписчика
            self.subscriber_activity[user_id] = {
                'subscribed_at': time.time(),
                'messages_received': 0,
                'last_activity': time.time()
            }
            
            # Создаем кнопку отписки
            keyboard = [[InlineKeyboardButton("\U0001F515 Отписаться", callback_data="unsubscribe")]]
            text = "<b> \U0001F514 Вы подписаны на уведомления от Discord-сервера 'Belomor' </b>\n\n<b> \U0001F916 Бот готов к работе! </b>"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение и закрепляем его
            sent_message = await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
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
                text="\U00002705 Чат очищен до закрепленного сообщения!"
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении /clean: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text="\U0000274C Ошибка при очистке чата"
            )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status - статистика бота"""
        user_id = update.effective_user.id
        
        try:
            uptime = time.time() - self.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            
            status_text = f"""
\U0001F4CA <b>Статистика бота</b>

\U0001F465 Подписчиков: <i>{len(self.subscribers)}</i>
\U0001F4E8 Переслано сообщений: <i>{self.message_count}</i>
\U000023F1 Время работы: <i>{uptime_hours}ч {uptime_minutes}м</i>
\U0001F514 Сервер: <i>{self.DISCORD_SERVER_NAME}</i>
\U000026A1 Интервал проверки: <i>{self.polling_interval} сек</i>
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
\U0001F4CA Статистика бота

\U0001F465 Подписчики: {len(self.subscribers)}
\U0001F507 Замьюченные: {muted_count}
\U0001F4E8 Сообщений переслано: {self.message_count}
\U000023F0 Время работы: {uptime_hours}ч {uptime_minutes}м
\U0001F4C5 Запущен: {datetime.fromtimestamp(self.start_time).strftime('%d.%m.%Y %H:%M')}

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
                text="\U0001F6AB Функция мьюта отключена администратором."
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
\U0001F507 Уведомления отключены

\U000023F0 До: {end_time_str}
\U0001F4C5 Длительность: {mute_duration // 3600}ч

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
\U0001F514 Уведомления включены

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
                    text="\U0001F514 У вас и так включены уведомления!"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обработке /unmute: {e}")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /admin - админ панель"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            if update.message:
                await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            logger.warning(f"Пользователь {user_id} пытался получить доступ к админ панели")
            return
        
        try:
            if update.message:
                await update.message.delete()
            
            # Создаем клавиатуру админ панели с категориями
            keyboard = [
                [InlineKeyboardButton("� Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("\U0001F465 Управление пользователями", callback_data="admin_users")],
                [InlineKeyboardButton("� Рассылка", callback_data="admin_broadcast_menu")],
                [InlineKeyboardButton("\U0001F5D1 Очистка чатов", callback_data="admin_clear_menu")],
                [InlineKeyboardButton("\U00002699 Системные команды", callback_data="admin_system")],
                [InlineKeyboardButton("\U0000274C Закрыть", callback_data="admin_close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Рассчитываем статистику
            uptime = time.time() - self.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            muted_count = len([uid for uid, end_time in self.muted_users.items() if end_time > time.time()])
            
            admin_text = f"""
<b>\U0001F6E0 Админ панель - Belomor Bot</b>

<b>� Быстрая статистика:</b>
\U0001F465 Подписчиков: <i>{len(self.subscribers)}</i>
�Замьючено: <i>{muted_count}</i>
\U0001F4E8 Сообщений: <i>{self.message_count}</i>
\U000023F1 Время работы: <i>{uptime_hours}ч {uptime_minutes}м</i>

Выберите действие ниже:
            """
            
            await context.bot.send_message(
                chat_id=user_id,
                text=admin_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /admin: {e}")
    
    async def admin_broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /broadcast - рассылка сообщения всем"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            # Проверяем аргументы
            if not context.args:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Использование: /broadcast <текст сообщения>\nПример: /broadcast Важное уведомление!"
                )
                return
            
            message_text = ' '.join(context.args)
            await update.message.delete()
            
            # Отправляем сообщение всем подписчикам
            success_count = 0
            for subscriber_id in self.subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=subscriber_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    success_count += 1
                    await asyncio.sleep(0.1)  # Небольшая пауза между отправками
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {subscriber_id}: {e}")
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 Сообщение отправлено {success_count} из {len(self.subscribers)} подписчикам"
            )
            
            logger.info(f"Администратор {user_id} отправил рассылку: {message_text}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /broadcast: {e}")
    
    async def admin_broadcast_html_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /broadcast_html - рассылка HTML сообщения всем"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            # Проверяем аргументы
            if not context.args:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Использование: /broadcast_html <текст сообщения с HTML>\nПример: /broadcast_html <b>Жирный текст</b>"
                )
                return
            
            message_text = ' '.join(context.args)
            await update.message.delete()
            
            # Отправляем сообщение всем подписчикам
            success_count = 0
            for subscriber_id in self.subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=subscriber_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    success_count += 1
                    await asyncio.sleep(0.1)  # Небольшая пауза между отправками
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {subscriber_id}: {e}")
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 HTML сообщение отправлено {success_count} из {len(self.subscribers)} подписчикам"
            )
            
            logger.info(f"Администратор {user_id} отправил HTML рассылку: {message_text}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /broadcast_html: {e}")
    
    async def admin_clear_old_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clear_old - удаление сообщений старше N часов"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            # Проверяем аргументы
            if not context.args:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Использование: /clear_old <часы>\nПример: /clear_old 24 (удалить сообщения старше 24 часов)"
                )
                return
            
            try:
                hours = int(context.args[0])
            except ValueError:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="\U0000274C Неверный формат. Укажите число часов."
                )
                return
            
            await update.message.delete()
            
            # Удаляем старые сообщения из sent_messages
            current_time = time.time()
            delete_threshold = hours * 3600
            deleted_count = 0
            
            messages_to_delete = []
            for (chat_id, message_id), sent_time in list(self.sent_messages.items()):
                if current_time - sent_time > delete_threshold:
                    messages_to_delete.append((chat_id, message_id))
            
            for chat_id, message_id in messages_to_delete:
                try:
                    await self.telegram_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    del self.sent_messages[(chat_id, message_id)]
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
                    if (chat_id, message_id) in self.sent_messages:
                        del self.sent_messages[(chat_id, message_id)]
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 Удалено {deleted_count} сообщений старше {hours} часов"
            )
            
            logger.info(f"Администратор {user_id} удалил {deleted_count} сообщений старше {hours} часов")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /clear_old: {e}")
    
    async def admin_mute_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /mute_user - замьютить конкретного пользователя"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            # Проверяем аргументы
            if len(context.args) < 2:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Использование: /mute_user <user_id> <часы>\nПример: /mute_user 123456789 24"
                )
                return
            
            target_user_id = context.args[0]
            try:
                hours = int(context.args[1])
            except ValueError:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="\U0000274C Неверный формат часов. Укажите число."
                )
                return
            
            await update.message.delete()
            
            # Устанавливаем мьют
            mute_end_time = time.time() + (hours * 3600)
            self.muted_users[int(target_user_id)] = mute_end_time
            
            end_time_str = datetime.fromtimestamp(mute_end_time).strftime('%d.%m.%Y %H:%M')
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 Пользователь {target_user_id} замьючен до {end_time_str}"
            )
            
            logger.info(f"Администратор {user_id} замьючил пользователя {target_user_id} на {hours} часов")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /mute_user: {e}")
    
    async def admin_unmute_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /unmute_user - размьютить конкретного пользователя"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            # Проверяем аргументы
            if not context.args:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Использование: /unmute_user <user_id>\nПример: /unmute_user 123456789"
                )
                return
            
            target_user_id = context.args[0]
            await update.message.delete()
            
            # Убираем мьют
            if int(target_user_id) in self.muted_users:
                del self.muted_users[int(target_user_id)]
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"\U00002705 Пользователь {target_user_id} размьючен"
                )
                logger.info(f"Администратор {user_id} размьючил пользователя {target_user_id}")
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"\U0000274C Пользователь {target_user_id} не замьючен"
                )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /unmute_user: {e}")
    
    async def admin_clearall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clearall - очистка всех чатов"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            await update.message.delete()
            
            # Очищаем чаты всех подписчиков
            cleared_count = 0
            for subscriber_id in self.subscribers:
                try:
                    await self.cleanup_chat_before_pinned(subscriber_id)
                    cleared_count += 1
                except Exception as e:
                    logger.error(f"Ошибка очистки чата пользователя {subscriber_id}: {e}")
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 Очищено {cleared_count} из {len(self.subscribers)} чатов"
            )
            
            logger.info(f"Администратор {user_id} очистил все чаты")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /clearall: {e}")
    
    async def admin_restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /restart - перезапуск бота"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🔄 Перезапуск бота..."
            )
            
            logger.info(f"Администратор {user_id} инициировал перезапуск бота")
            
            # Перезапуск бота через exit
            import sys
            import os
            os.execv(sys.executable, [sys.executable] + sys.argv)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /restart: {e}")
    
    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /logs - вывод последних логов"""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        try:
            await update.message.delete()
            
            # Получаем последние логи из памяти
            if hasattr(self, 'logs_buffer'):
                logs_text = "\n".join(self.logs_buffer[-50:])  # Последние 50 строк
            else:
                logs_text = "Логи не найдены"
            
            # Разбиваем на части, если сообщение слишком длинное
            max_length = 4000
            logs_parts = [logs_text[i:i+max_length] for i in range(0, len(logs_text), max_length)]
            
            for i, part in enumerate(logs_parts, 1):
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"<b>📋 Логи (часть {i}/{len(logs_parts)}):</b>\n\n<pre>{part}</pre>",
                    parse_mode='HTML'
                )
            
            logger.info(f"Администратор {user_id} запросил логи")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /logs: {e}")
    
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
                keyboard = [[InlineKeyboardButton("\U0001F515 Отписаться", callback_data="unsubscribe")]]
                text = f"\U0001F514 Вы успешно подписались на уведомления от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
                
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
                
                # Удаляем статистику подписчика
                if user_id in self.subscriber_activity:
                    del self.subscriber_activity[user_id]
                
                # Редактируем сообщение
                keyboard = [[InlineKeyboardButton("\U0001F514 Подписаться", callback_data="subscribe")]]
                text = f"\U0001F515 Вы успешно отписались от уведомлений от Discord-сервера '{self.DISCORD_SERVER_NAME}'"
                
                await query.edit_message_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Пользователь {user_id} отписался от уведомлений")
            
            elif query.data == "admin_stats":
                # Админ: статистика
                uptime = time.time() - self.start_time
                uptime_hours = int(uptime // 3600)
                uptime_minutes = int((uptime % 3600) // 60)
                muted_count = len([uid for uid, end_time in self.muted_users.items() if end_time > time.time()])
                
                stats_text = f"""
<b>\U0001F4CA Детальная статистика бота</b>

<b>\U0001F465Пользователи:</b>
• Подписчиков: <i>{len(self.subscribers)}</i>
•Замьючено: <i>{muted_count}</i>

<b>\U0001F4E8 Сообщения:</b>
• Переслано: <i>{self.message_count}</i>
• Интервал проверки: <i>{self.polling_interval} сек</i>

<b>\U000023F1 Время работы:</b>
• Запущен: <i>{datetime.fromtimestamp(self.start_time).strftime('%d.%m.%Y %H:%M')}</i>
• Аптайм: <i>{uptime_hours}ч {uptime_minutes}м</i>

<b>\U0001F527 Настройки:</b>
• Батч размер: <i>{self.batch_size}</i>
• Макс. отправок: <i>{self.max_concurrent_sends}</i>
• Автоудаление: <i>{'Включено' if self.auto_delete_enabled else 'Выключено'}</i>
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F504 Обновить", callback_data="admin_stats")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=stats_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_users":
                # Админ: управление пользователями
                users_text = f"""
<b>\U0001F465 Управление пользователями</b>

Всего подписчиков: <i>{len(self.subscribers)}</i>
Замьючено: <i>{len([uid for uid, end_time in self.muted_users.items() if end_time > time.time()])}</i>

Выберите действие:
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F4CB Подписчики с уведомлениями", callback_data="admin_subscribers_enabled")],
                    [InlineKeyboardButton("\U0001F507 Подписчики без уведомлений", callback_data="admin_subscribers_disabled")],
                    [InlineKeyboardButton("� Активность подписчиков", callback_data="admin_activity")],
                    [InlineKeyboardButton("\U0001F9F9 Очистить неактивных (30дней)", callback_data="admin_cleanup_inactive")],
                    [InlineKeyboardButton("� Размьютить всех", callback_data="admin_unmute_all")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=users_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_activity":
                # Админ: статистика активности подписчиков
                activity_text = "<b>\U0001F4CA Активность подписчиков</b>\n\n"
                
                if self.subscriber_activity:
                    # Сортируем по последней активности
                    sorted_activity = sorted(
                        self.subscriber_activity.items(),
                        key=lambda x: x[1]['last_activity'],
                        reverse=True
                    )
                    
                    for i, (user_id, data) in enumerate(sorted_activity[:20], 1):
                        subscribed = datetime.fromtimestamp(data['subscribed_at']).strftime('%d.%m.%Y')
                        last_active = datetime.fromtimestamp(data['last_activity']).strftime('%d.%m.%Y %H:%M')
                        messages = data['messages_received']
                        activity_text += f"{i}. <code>{user_id}</code>\n   \U0001F4C5 Подписан: {subscribed}\n   \U0001F4E8 Сообщений: {messages}\n   \U000023F0 Активность: {last_active}\n\n"
                    
                    if len(sorted_activity) > 20:
                        activity_text += f"<i>...и еще {len(sorted_activity) - 20} пользователей</i>"
                else:
                    activity_text += "Нет данных об активности"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=activity_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_cleanup_inactive":
                # Админ: очистка неактивных подписчиков (30 дней)
                current_time = time.time()
                thirty_days_ago = current_time - (30 * 24 * 3600)
                
                inactive_users = [
                    uid for uid, data in self.subscriber_activity.items()
                    if data['last_activity'] < thirty_days_ago
                ]
                
                if inactive_users:
                    for uid in inactive_users:
                        self.subscribers.discard(uid)
                        if uid in self.subscriber_activity:
                            del self.subscriber_activity[uid]
                    
                    self.save_subscribers()
                    result_text = f"\U00002705 Удалено {len(inactive_users)} неактивных подписчиков"
                else:
                    result_text = "\U0000274C Нет неактивных подписчиков"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=result_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Администратор {user_id} очистил {len(inactive_users)} неактивных подписчиков")
            
            elif query.data == "admin_subscribers_enabled":
                # Админ: список подписчиков с включенными уведомлениями
                current_time = time.time()
                enabled_users = [uid for uid in self.subscribers if uid not in self.muted_users or self.muted_users[uid] < current_time]
                
                if enabled_users:
                    list_text = f"<b>\U0001F514 Люди, у которых включены уведомления</b>\n\n"
                    for i, user_id in enumerate(enabled_users[:50], 1):
                        list_text += f"{i}. <i>ID: {user_id}</i>\n"
                    
                    if len(enabled_users) > 50:
                        list_text += f"\n<i>...и еще {len(enabled_users) - 50} пользователей</i>"
                else:
                    list_text = "<b>\U0001F514 Люди, у которых включены уведомления</b>\n\nНет пользователей с включенными уведомлениями"
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F507 Выключенные уведомления", callback_data="admin_subscribers_disabled")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=list_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_subscribers_disabled":
                # Админ: список подписчиков с выключенными уведомлениями
                current_time = time.time()
                disabled_users = [uid for uid in self.subscribers if uid in self.muted_users and self.muted_users[uid] > current_time]
                
                if disabled_users:
                    list_text = f"<b>\U0001F507 Люди, у которых выключены уведомления</b>\n\n"
                    for i, user_id in enumerate(disabled_users[:50], 1):
                        mute_end = self.muted_users[user_id]
                        end_time_str = datetime.fromtimestamp(mute_end).strftime('%d.%m.%Y %H:%M')
                        list_text += f"{i}. <i>ID: {user_id}</i> - до {end_time_str}\n"
                    
                    if len(disabled_users) > 50:
                        list_text += f"\n<i>...и еще {len(disabled_users) - 50} пользователей</i>"
                else:
                    list_text = "<b>\U0001F507 Люди, у которых выключены уведомления</b>\n\nНет пользователей с выключенными уведомлениями"
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F514 Включенные уведомления", callback_data="admin_subscribers_enabled")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=list_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_unmute_all":
                # Админ: размьютить всех
                current_time = time.time()
                muted_count = len([uid for uid, end_time in self.muted_users.items() if end_time > current_time])
                
                if muted_count == 0:
                    result_text = "\U0000274C Нет замьюченных пользователей"
                else:
                    self.muted_users.clear()
                    result_text = f"\U00002705 Размьючено {muted_count} пользователей"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=result_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Администратор {user_id} размьючил всех пользователей")
            
            elif query.data == "admin_users_list":
                # Админ: список подписчиков
                subscribers_list = list(self.subscribers)
                if len(subscribers_list) > 50:
                    list_text = f"<b>\U0001F4CB Список подписчиков (первые 50 из {len(subscribers_list)})</b>\n\n"
                else:
                    list_text = f"<b>\U0001F4CB Список подписчиков ({len(subscribers_list)})</b>\n\n"
                
                for i, sub_id in enumerate(subscribers_list[:50], 1):
                    list_text += f"{i}. <code>{sub_id}</code>\n"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=list_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_muted_list":
                # Админ: список замьюченных
                current_time = time.time()
                muted_list = [(uid, end_time) for uid, end_time in self.muted_users.items() if end_time > current_time]
                
                if muted_list:
                    list_text = f"<b>\U0001F507 Список замьюченных ({len(muted_list)})</b>\n\n"
                    for i, (uid, end_time) in enumerate(muted_list, 1):
                        end_str = datetime.fromtimestamp(end_time).strftime('%d.%m.%Y %H:%M')
                        list_text += f"{i}. <code>{uid}</code> - до {end_str}\n"
                else:
                    list_text = "<b>\U0001F507 Список замьюченных</b>\n\nНет замьюченных пользователей"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
                ]
                
                await query.edit_message_text(
                    text=list_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_broadcast_menu":
                # Админ: меню рассылки
                broadcast_text = """
<b>\U0001F4E2 Рассылка сообщений</b>

Выберите тип рассылки:
• <b>Текстовая</b> - обычное текстовое сообщение
• <b>HTML</b> - сообщение с форматированием
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F4DD Текстовая", callback_data="admin_broadcast_type_text")],
                    [InlineKeyboardButton("\U0001F3A8 HTML", callback_data="admin_broadcast_type_html")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=broadcast_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_broadcast_type_text":
                # Админ: ввод текстовой рассылки
                await query.edit_message_text(
                    text="\U0001F4DD Введите текст для рассылки:\n\nОтправьте сообщение как обычный текст, и оно будет разослано всем подписчикам.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Отмена", callback_data="admin_back")]])
                )
                # Сохраняем состояние для следующего сообщения
                context.user_data['waiting_for_broadcast'] = 'text'
            
            elif query.data == "admin_broadcast_type_html":
                # Админ: ввод HTML рассылки
                await query.edit_message_text(
                    text="\U0001F3A8 Введите HTML текст для рассылки:\n\nОтправьте сообщение с HTML тегами, и оно будет разослано всем подписчикам.\nПример: <b>Жирный текст</b> и <i>курсив</i>",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Отмена", callback_data="admin_back")]])
                )
                # Сохраняем состояние для следующего сообщения
                context.user_data['waiting_for_broadcast'] = 'html'
            
            elif query.data == "admin_clear_menu":
                # Админ: меню очистки
                clear_text = """
<b>\U0001F5D1 Очистка чатов</b>

Выберите действие:
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F5D1 Очистить все чаты", callback_data="admin_clearall_confirm")],
                    [InlineKeyboardButton("\U0001F9F9 Удалить старые (24ч)", callback_data="admin_clear_old_24")],
                    [InlineKeyboardButton("\U0001F9F9 Удалить старые (12ч)", callback_data="admin_clear_old_12")],
                    [InlineKeyboardButton("\U0001F9F9 Удалить старые (6ч)", callback_data="admin_clear_old_6")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=clear_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data.startswith("admin_clear_old_"):
                # Админ: удаление старых сообщений
                hours = int(query.data.split("_")[-1])
                current_time = time.time()
                delete_threshold = hours * 3600
                deleted_count = 0
                
                messages_to_delete = []
                for (chat_id, message_id), sent_time in list(self.sent_messages.items()):
                    if current_time - sent_time > delete_threshold:
                        messages_to_delete.append((chat_id, message_id))
                
                for chat_id, message_id in messages_to_delete:
                    try:
                        await self.telegram_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                        del self.sent_messages[(chat_id, message_id)]
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
                        if (chat_id, message_id) in self.sent_messages:
                            del self.sent_messages[(chat_id, message_id)]
                
                result_text = f"\U00002705 Удалено {deleted_count} сообщений старше {hours} часов"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_clear_menu")]
                ]
                
                await query.edit_message_text(
                    text=result_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Администратор {user_id} удалил {deleted_count} сообщений старше {hours} часов через панель")
            
            elif query.data == "admin_clearall_confirm":
                # Админ: подтверждение очистки
                confirm_text = """
\U000026A0 <b>Вы уверены, что хотите очистить ВСЕ чаты?</b>

Это действие удалит все сообщения до закрепленных у всех подписчиков!
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U00002705 Да, очистить", callback_data="admin_clearall_do")],
                    [InlineKeyboardButton("\U0000274C Отмена", callback_data="admin_clear_menu")]
                ]
                
                await query.edit_message_text(
                    text=confirm_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_clearall_do":
                # Админ: выполнить очистку
                cleared_count = 0
                for subscriber_id in self.subscribers:
                    try:
                        await self.cleanup_chat_before_pinned(subscriber_id)
                        cleared_count += 1
                    except Exception as e:
                        logger.error(f"Ошибка очистки чата пользователя {subscriber_id}: {e}")
                
                result_text = f"\U00002705 Очищено {cleared_count} из {len(self.subscribers)} чатов"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=result_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info(f"Администратор {user_id} очистил все чаты через панель")
            
            elif query.data == "admin_system":
                # Админ: системные команды
                system_text = """
<b>\U00002699 Системные команды</b>

Доступные команды:
• <b>/restart</b> - перезапустить бота
• <b>/status</b> - показать статус бота
• <b>/stats</b> - детальная статистика

\U000026A0 Будьте осторожны с системными командами!
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F504 Перезапустить бота", callback_data="admin_restart_confirm")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=system_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_restart_confirm":
                # Админ: подтверждение перезапуска
                confirm_text = """
\U000026A0 <b>Вы уверены, что хотите перезапустить бота?</b>

Бот будет перезапущен через несколько секунд.
                """
                
                keyboard = [
                    [InlineKeyboardButton("\U00002705 Да, перезапустить", callback_data="admin_restart_do")],
                    [InlineKeyboardButton("\U0000274C Отмена", callback_data="admin_system")]
                ]
                
                await query.edit_message_text(
                    text=confirm_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_restart_do":
                # Админ: выполнить перезапуск
                await query.edit_message_text(
                    text="🔄 Перезапуск бота...",
                    reply_markup=None
                )
                
                logger.info(f"Администратор {user_id} перезапустил бота через панель")
                
                # Перезапуск бота
                import sys
                import os
                os.execv(sys.executable, [sys.executable] + sys.argv)
            
            elif query.data == "admin_back":
                # Админ: назад в главное меню
                # Показываем главное меню напрямую
                user_id = query.from_user.id
                
                # Рассчитываем статистику
                uptime = time.time() - self.start_time
                uptime_hours = int(uptime // 3600)
                uptime_minutes = int((uptime % 3600) // 60)
                muted_count = len([uid for uid, end_time in self.muted_users.items() if end_time > time.time()])
                
                # Создаем клавиатуру админ панели с категориями
                keyboard = [
                    [InlineKeyboardButton("\U0001F4CA Статистика", callback_data="admin_stats")],
                    [InlineKeyboardButton("\U0001F465 Управление пользователями", callback_data="admin_users")],
                    [InlineKeyboardButton("\U0001F4E2 Рассылка", callback_data="admin_broadcast_menu")],
                    [InlineKeyboardButton("\U0001F5D1 Очистка чатов", callback_data="admin_clear_menu")],
                    [InlineKeyboardButton("\U00002699 Системные команды", callback_data="admin_system")],
                    [InlineKeyboardButton("\U0000274C Закрыть", callback_data="admin_close")]
                ]
                
                admin_text = f"""
<b>\U0001F6E0 Админ панель - Belomor Bot</b>

<b>\U0001F4CA Быстрая статистика:</b>
\U0001F465 Подписчиков: <i>{len(self.subscribers)}</i>
\U0001F507Замьючено: <i>{muted_count}</i>
\U0001F4E8 Сообщений: <i>{self.message_count}</i>
\U000023F1 Время работы: <i>{uptime_hours}ч {uptime_minutes}м</i>

Выберите действие ниже:
                """
                
                await query.edit_message_text(
                    text=admin_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_close":
                # Админ: закрыть панель
                await query.edit_message_text(
                    text="\U0000274C Админ панель закрыта",
                    reply_markup=None
                )
            
            elif query.data == "admin_broadcast":
                # Админ: рассылка (старый метод для совместимости)
                await query.edit_message_text(
                    text="\U0001F4E2 Введите сообщение для рассылки:\nИспользуйте: /broadcast <текст>",
                    reply_markup=None
                )
            
            elif query.data == "admin_clearall":
                # Админ: очистить все чаты (старый метод для совместимости)
                await query.edit_message_text(
                    text="\U0001F5D1 Очистка всех чатов...\nИспользуйте: /clearall",
                    reply_markup=None
                )
            
            elif query.data == "admin_restart":
                # Админ: перезапуск бота (старый метод для совместимости)
                await query.edit_message_text(
                    text="\U0001F504 Перезапуск бота...\nИспользуйте: /restart",
                    reply_markup=None
                )
            
            elif query.data == "admin_templates":
                # Админ: управление шаблонами рассылки
                templates_text = "<b>\U0001F4DD Шаблоны рассылки</b>\n\n"
                
                if self.broadcast_templates:
                    for name, text in self.broadcast_templates.items():
                        preview = text[:50] + "..." if len(text) > 50 else text
                        templates_text += f"• <b>{name}</b>: {preview}\n"
                else:
                    templates_text += "Нет сохраненных шаблонов"
                
                keyboard = [
                    [InlineKeyboardButton("\U00002795 Добавить шаблон", callback_data="admin_template_add")],
                    [InlineKeyboardButton("\U0001F5D1 Удалить шаблон", callback_data="admin_template_delete")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=templates_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_template_add":
                # Админ: добавление шаблона
                await query.edit_message_text(
                    text="\U0001F4DD Введите название шаблона и текст через |:\n\nПример: Название|Текст шаблона",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Отмена", callback_data="admin_templates")]])
                )
                context.user_data['waiting_for_template'] = True
            
            elif query.data == "admin_template_delete":
                # Админ: удаление шаблона
                if self.broadcast_templates:
                    delete_text = "<b>\U0001F5D1 Выберите шаблон для удаления:</b>\n\n"
                    keyboard = []
                    for name in self.broadcast_templates.keys():
                        keyboard.append([InlineKeyboardButton(f"\U0001F5D1 {name}", callback_data=f"admin_template_del_{name}")])
                    keyboard.append([InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_templates")])
                    
                    await query.edit_message_text(
                        text=delete_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                else:
                    await query.edit_message_text(
                        text="\U0000274C Нет шаблонов для удаления",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_templates")]])
                    )
            
            elif query.data.startswith("admin_template_del_"):
                # Админ: удаление конкретного шаблона
                template_name = query.data.replace("admin_template_del_", "")
                if template_name in self.broadcast_templates:
                    del self.broadcast_templates[template_name]
                    result_text = f"\U00002705 Шаблон '{template_name}' удален"
                else:
                    result_text = "\U0000274C Шаблон не найден"
                
                await query.edit_message_text(
                    text=result_text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_templates")]])
                )
            
            elif query.data == "admin_log":
                # Админ: лог действий
                log_text = "<b>\U0001F4CB Лог действий админа</b>\n\n"
                
                if self.admin_log:
                    for log_entry in self.admin_log[-20:]:  # Последние 20 записей
                        timestamp = datetime.fromtimestamp(log_entry['timestamp']).strftime('%d.%m.%Y %H:%M:%S')
                        log_text += f"<b>{timestamp}</b>\n{log_entry['action']}: {log_entry['details']}\n\n"
                else:
                    log_text += "Нет записей в логе"
                
                keyboard = [
                    [InlineKeyboardButton("\U0001F5D1 Очистить лог", callback_data="admin_log_clear")],
                    [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
                ]
                
                await query.edit_message_text(
                    text=log_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            
            elif query.data == "admin_log_clear":
                # Админ: очистка лога
                self.admin_log.clear()
                await query.edit_message_text(
                    text="\U00002705 Лог очищен",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]])
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки: {e}")
    
    async def handle_all_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик всех сообщений кроме команд"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получено сообщение от пользователя {user_id} ({user_name})")
        
        try:
            # Проверяем, ждет ли админ текст для шаблона
            if user_id == self.ADMIN_ID and context.user_data.get('waiting_for_template'):
                template_input = update.message.text
                
                await update.message.delete()
                
                if '|' in template_input:
                    name, text = template_input.split('|', 1)
                    self.broadcast_templates[name.strip()] = text.strip()
                    
                    # Логируем действие
                    self.admin_log.append({
                        'timestamp': time.time(),
                        'action': 'Добавлен шаблон',
                        'details': f'Название: {name.strip()}'
                    })
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"\U00002705 Шаблон '{name.strip()}' добавлен"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="\U0000274C Неверный формат. Используйте: Название|Текст"
                    )
                
                del context.user_data['waiting_for_template']
                return
            
            # Проверяем, ждет ли админ текст для рассылки
            if user_id == self.ADMIN_ID and context.user_data.get('waiting_for_broadcast'):
                broadcast_type = context.user_data['waiting_for_broadcast']
                message_text = update.message.text
                
                await update.message.delete()
                
                # Отправляем рассылку
                success_count = 0
                parse_mode = 'HTML' if broadcast_type == 'html' else None
                
                for subscriber_id in self.subscribers:
                    try:
                        await context.bot.send_message(
                            chat_id=subscriber_id,
                            text=message_text,
                            parse_mode=parse_mode
                        )
                        success_count += 1
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Ошибка отправки пользователю {subscriber_id}: {e}")
                
                # Логируем рассылку
                self.admin_log.append({
                    'timestamp': time.time(),
                    'action': 'Рассылка',
                    'details': f'Тип: {broadcast_type}, Получили: {success_count}/{len(self.subscribers)}'
                })
                
                # Очищаем состояние
                del context.user_data['waiting_for_broadcast']
                
                # Отправляем результат
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"\U00002705 Сообщение отправлено {success_count} из {len(self.subscribers)} подписчикам"
                )
                
                logger.info(f"Администратор {user_id} отправил {broadcast_type} рассылку через панель")
                return
            
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
    application.add_handler(CommandHandler("admin", bot.admin_command))
    application.add_handler(CommandHandler("broadcast", bot.admin_broadcast_command))
    application.add_handler(CommandHandler("broadcast_html", bot.admin_broadcast_html_command))
    application.add_handler(CommandHandler("clearall", bot.admin_clearall_command))
    application.add_handler(CommandHandler("clear_old", bot.admin_clear_old_command))
    application.add_handler(CommandHandler("mute_user", bot.admin_mute_user_command))
    application.add_handler(CommandHandler("unmute_user", bot.admin_unmute_user_command))
    application.add_handler(CommandHandler("restart", bot.admin_restart_command))
    application.add_handler(CommandHandler("logs", bot.logs_command))
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












