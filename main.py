"""Главный файл бота Discord-Telegram моста."""

import os
import asyncio
import logging
import time
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv

# Импорты модулей
from config.config import Config
from api.discord_api import DiscordAPI
from handlers.telegram_handlers import TelegramHandlers
from handlers.admin_handlers import AdminHandlers
from handlers.callback_handlers import CallbackHandlers
from utils.utils import (
    get_current_time,
    load_subscribers,
    save_subscribers,
    load_subscriber_activity,
    save_subscriber_activity,
    load_muted_users,
    save_muted_users,
    load_broadcast_templates,
    save_broadcast_templates,
    load_admin_log,
    save_admin_log
)

# Настройка логирования
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscordTelegramBot:
    """Главный класс бота."""
    
    def __init__(self):
        """Инициализация бота."""
        # Загружаем конфигурацию
        self.config = Config()
        
        # Инициализируем Discord API
        self.discord_api = DiscordAPI(self.config)
        
        # Инициализируем обработчики
        self.telegram_handlers = TelegramHandlers(self)
        self.admin_handlers = AdminHandlers(self)
        self.callback_handlers = CallbackHandlers(self)
        
        # Директория для данных
        self.data_dir = os.getenv('DATA_DIR', './data')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # Хранилище подписчиков и сообщений
        self.subscribers = load_subscribers(self.data_dir)
        self.user_messages = {}  # ID пользователя -> ID сообщения для редактирования
        self.muted_users = load_muted_users(self.data_dir)
        self.last_message_id = None
        self.start_time = time.time()
        self.message_count = 0
        
        # Статистика активности подписчиков
        self.subscriber_activity = load_subscriber_activity(self.data_dir)
        
        # Шаблоны рассылок
        self.broadcast_templates = load_broadcast_templates(self.data_dir)
        
        # Лог действий админа
        self.admin_log = load_admin_log(self.data_dir)
        
        # Хранилище отправленных сообщений для автоудаления
        self.sent_messages = {}  # {(chat_id, message_id): timestamp}
        
        # Telegram приложение
        self.telegram_app = None
        
        logger.info("Бот инициализирован")
    
    def get_current_time(self):
        """Возвращает текущее время."""
        return get_current_time()
    
    def save_subscribers(self):
        """Сохраняет подписчиков."""
        save_subscribers(self.subscribers, self.data_dir)
    
    def save_subscriber_activity(self):
        """Сохраняет активность подписчиков."""
        save_subscriber_activity(self.subscriber_activity, self.data_dir)
    
    def save_muted_users(self):
        """Сохраняет замьюченных пользователей."""
        save_muted_users(self.muted_users, self.data_dir)
    
    def save_broadcast_templates(self):
        """Сохраняет шаблоны рассылки."""
        save_broadcast_templates(self.broadcast_templates, self.data_dir)
    
    def save_admin_log(self):
        """Сохраняет лог админа."""
        save_admin_log(self.admin_log, self.data_dir)
    
    async def cleanup_chat_before_pinned(self, chat_id):
        """Очищает чат до закрепленного сообщения."""
        try:
            # Получаем закрепленное сообщение
            pinned_messages = await self.telegram_app.bot.get_chat(chat_id).pinned_message
            
            if pinned_messages:
                pinned_message_id = pinned_messages.message_id
                
                # Получаем все сообщения в чате
                messages = []
                async for message in self.telegram_app.bot.get_chat_history(chat_id, limit=100):
                    messages.append(message)
                
                # Удаляем все сообщения до закрепленного
                for message in messages:
                    if message.message_id < pinned_message_id:
                        try:
                            await self.telegram_app.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
                            if (chat_id, message.message_id) in self.sent_messages:
                                del self.sent_messages[(chat_id, message.message_id)]
                        except Exception as e:
                            logger.error(f"Ошибка удаления сообщения {message.message_id}: {e}")
                            if (chat_id, message.message_id) in self.sent_messages:
                                del self.sent_messages[(chat_id, message.message_id)]
        except Exception as e:
            logger.error(f"Ошибка очистки чата {chat_id}: {e}")
    
    async def send_message_to_user(self, user_id, text, reply_markup=None, parse_mode=None):
        """Отправляет сообщение пользователю."""
        try:
            message = await self.telegram_app.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            
            if self.config.AUTO_DELETE_ENABLED:
                self.sent_messages[(user_id, message.message_id)] = self.get_current_time()
            
            return message
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
            return None
    
    async def poll_discord_messages(self):
        """Получает сообщения из Discord и пересылает в Telegram."""
        logger.info("Запущен поток получения сообщений из Discord")
        
        while True:
            try:
                # Получаем сообщения из Discord
                messages = self.discord_api.get_messages()
                
                if messages:
                    # Фильтруем новые сообщения
                    new_messages = []
                    for message in messages:
                        message_id = message.get('id')
                        if message_id != self.last_message_id:
                            new_messages.append(message)
                    
                    if new_messages:
                        # Обновляем last_message_id
                        self.last_message_id = new_messages[0].get('id')
                        
                        # Обрабатываем сообщения в обратном порядке (от старых к новым)
                        for message in reversed(new_messages):
                            await self.process_discord_message(message)
                
                # Ждем перед следующим опросом
                await asyncio.sleep(self.config.POLLING_INTERVAL)
                
            except Exception as e:
                logger.error(f"Ошибка при получении сообщений из Discord: {e}")
                await asyncio.sleep(self.config.POLLING_INTERVAL)
    
    async def process_discord_message(self, message):
        """Обрабатывает сообщение из Discord."""
        try:
            # Форматируем сообщение
            content, author_display_name, msk_time = self.discord_api.format_message(message)
            
            if not content:
                return
            
            # Получаем вложения
            attachments = self.discord_api.get_attachments(message)
            
            # Формируем текст сообщения для Telegram
            telegram_text = f"<b>{author_display_name}</b>\n{content}\n\n<i>{msk_time}</i>"
            
            if attachments and self.config.ATTACHMENTS_ENABLED:
                telegram_text += f"\n\n📎 Вложения: {len(attachments)}"
                for attachment_url in attachments:
                    telegram_text += f"\n{attachment_url}"
            
            # Отправляем сообщение подписчикам
            current_time = self.get_current_time()
            success_count = 0
            
            for user_id in self.subscribers:
                # Проверяем, не замьючен ли пользователь
                if user_id in self.muted_users and self.muted_users[user_id] > current_time:
                    continue
                
                try:
                    await self.send_message_to_user(
                        user_id=user_id,
                        text=telegram_text,
                        parse_mode='HTML'
                    )
                    success_count += 1
                    
                    # Обновляем статистику активности
                    if user_id in self.subscriber_activity:
                        self.subscriber_activity[user_id]['messages_received'] += 1
                        self.subscriber_activity[user_id]['last_activity'] = current_time
                    
                    # Пауза между отправками
                    await asyncio.sleep(self.config.BATCH_DELAY)
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
            
            self.message_count += 1
            logger.info(f"Сообщение переслано {success_count} из {len(self.subscribers)} подписчикам")
            
            # Сохраняем статистику
            self.save_subscriber_activity()
            
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения из Discord: {e}")
    
    async def handle_all_messages(self, update, context):
        """Обработчик всех сообщений кроме команд."""
        user_id = update.effective_user.id
        
        # Проверяем, ждет ли админ текст для шаблона
        if user_id == self.config.ADMIN_ID and context.user_data.get('waiting_for_template'):
            message_text = update.message.text
            
            if '|' in message_text:
                name, text = message_text.split('|', 1)
                name = name.strip()
                text = text.strip()
                
                self.broadcast_templates[name] = text
                self.save_broadcast_templates()
                
                # Логируем действие
                self.admin_log.append({
                    'timestamp': self.get_current_time(),
                    'action': 'Добавлен шаблон',
                    'details': f'Название: {name}'
                })
                self.save_admin_log()
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"\U00002705 Шаблон '{name}' добавлен"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="\U0000274C Неверный формат. Используйте: Название|Текст"
                )
            
            del context.user_data['waiting_for_template']
            return
        
        # Проверяем, ждет ли админ текст для рассылки
        if user_id == self.config.ADMIN_ID and context.user_data.get('waiting_for_broadcast'):
            broadcast_type = context.user_data['waiting_for_broadcast']
            message_text = update.message.text
            
            success_count = 0
            current_time = self.get_current_time()
            
            for subscriber_id in self.subscribers:
                # Проверяем, не замьючен ли пользователь
                if subscriber_id in self.muted_users and self.muted_users[subscriber_id] > current_time:
                    continue
                
                try:
                    if broadcast_type == 'html':
                        await context.bot.send_message(
                            chat_id=subscriber_id,
                            text=message_text,
                            parse_mode='HTML'
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=subscriber_id,
                            text=message_text
                        )
                    success_count += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {subscriber_id}: {e}")
            
            # Логируем действие
            self.admin_log.append({
                'timestamp': self.get_current_time(),
                'action': 'Рассылка',
                'details': f'Тип: {broadcast_type}, Получили: {success_count}/{len(self.subscribers)}'
            })
            self.save_admin_log()
            
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
            text=error_message
        )
    
    async def auto_delete_old_messages(self):
        """Автоматически удаляет старые сообщения."""
        if not self.config.AUTO_DELETE_ENABLED:
            return
        
        logger.info("Запущен поток автоудаления старых сообщений")
        
        while True:
            try:
                current_time = self.get_current_time()
                delete_threshold = self.config.AUTO_DELETE_HOURS * 3600
                
                deleted_count = 0
                for (chat_id, message_id), sent_time in list(self.sent_messages.items()):
                    if current_time - sent_time > delete_threshold:
                        try:
                            await self.telegram_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                            del self.sent_messages[(chat_id, message_id)]
                            deleted_count += 1
                        except Exception as e:
                            logger.error(f"Ошибка автоудаления сообщения {message_id}: {e}")
                            if (chat_id, message_id) in self.sent_messages:
                                del self.sent_messages[(chat_id, message_id)]
                
                if deleted_count > 0:
                    logger.info(f"Автоудалено {deleted_count} старых сообщений")
                
                # Проверяем каждый час
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Ошибка в потоке автоудаления: {e}")
                await asyncio.sleep(3600)
    
    def run(self):
        """Запускает бота."""
        logger.info("Запуск бота...")
        
        # Создаем Telegram приложение
        self.telegram_app = Application.builder().token(self.config.TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики команд
        self.telegram_app.add_handler(CommandHandler("start", self.telegram_handlers.start_command))
        self.telegram_app.add_handler(CommandHandler("clean", self.telegram_handlers.clean_command))
        self.telegram_app.add_handler(CommandHandler("status", self.telegram_handlers.status_command))
        self.telegram_app.add_handler(CommandHandler("mute", self.telegram_handlers.mute_command))
        self.telegram_app.add_handler(CommandHandler("unmute", self.telegram_handlers.unmute_command))
        
        # Админ команды
        self.telegram_app.add_handler(CommandHandler("stats", self.admin_handlers.stats_command))
        self.telegram_app.add_handler(CommandHandler("admin", self.admin_handlers.admin_command))
        self.telegram_app.add_handler(CommandHandler("broadcast", self.admin_handlers.broadcast_command))
        self.telegram_app.add_handler(CommandHandler("broadcast_html", self.admin_handlers.broadcast_html_command))
        self.telegram_app.add_handler(CommandHandler("clear_old", self.admin_handlers.clear_old_command))
        self.telegram_app.add_handler(CommandHandler("mute_user", self.admin_handlers.mute_user_command))
        self.telegram_app.add_handler(CommandHandler("unmute_user", self.admin_handlers.unmute_user_command))
        self.telegram_app.add_handler(CommandHandler("clearall", self.admin_handlers.clearall_command))
        self.telegram_app.add_handler(CommandHandler("restart", self.admin_handlers.restart_command))
        
        # Обработчик кнопок
        self.telegram_app.add_handler(CallbackQueryHandler(self.callback_handlers.button_callback))
        
        # Обработчик всех сообщений
        self.telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_all_messages))
        
        # Запускаем фоновые задачи
        self.telegram_app.job_queue.run_once(lambda ctx: asyncio.create_task(self.poll_discord_messages()), 1)
        self.telegram_app.job_queue.run_once(lambda ctx: asyncio.create_task(self.auto_delete_old_messages()), 2)
        
        # Запускаем бота
        logger.info("Бот запущен")
        self.telegram_app.run_polling()


if __name__ == "__main__":
    bot = DiscordTelegramBot()
    bot.run()
