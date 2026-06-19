"""Модуль для обработчиков команд Telegram."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class TelegramHandlers:
    """Класс для обработчиков команд Telegram."""
    
    def __init__(self, bot):
        """Инициализация обработчиков.
        
        Args:
            bot: Экземпляр бота
        """
        self.bot = bot
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start - моментальная подписка."""
        # Проверяем, включена ли функция подписок
        if not self.bot.config.SUBSCRIPTIONS_ENABLED:
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
            if user_id in self.bot.user_messages:
                logger.info(f"Пользователь {user_id} уже использует бота")
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ Вы уже подписаны на уведомления!"
                )
                return
            
            # Моментально подписываем пользователя
            self.bot.subscribers.add(user_id)
            self.bot.save_subscribers()
            
            # Записываем активность подписчика
            self.bot.subscriber_activity[user_id] = {
                'subscribed_at': self.bot.get_current_time(),
                'messages_received': 0,
                'last_activity': self.bot.get_current_time()
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
            
            # Сохраняем ID сообщения
            self.bot.user_messages[user_id] = sent_message.message_id
            if self.bot.config.AUTO_DELETE_ENABLED:
                self.bot.sent_messages[(user_id, sent_message.message_id)] = self.bot.get_current_time()
            
            logger.info(f"Пользователь {user_id} подписался на уведомления через /start")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /start: {e}")
    
    async def clean_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clean - очистка чата до закрепленного сообщения."""
        user_id = update.effective_user.id
        
        try:
            await update.message.delete()
            await self.bot.cleanup_chat_before_pinned(user_id)
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
        """Обработчик команды /status - статистика бота."""
        user_id = update.effective_user.id
        
        try:
            uptime = self.bot.get_current_time() - self.bot.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            
            status_text = f"""
📊 <b>Статистика бота</b>

👥 Подписчиков: <i>{len(self.bot.subscribers)}</i>
📨 Переслано сообщений: <i>{self.bot.message_count}</i>
⏱️ Время работы: <i>{uptime_hours}ч {uptime_minutes}м</i>
🔔 Сервер: <i>{self.bot.config.DISCORD_SERVER_NAME}</i>
⚡ Интервал проверки: <i>{self.bot.config.POLLING_INTERVAL} сек</i>
            """
            
            await context.bot.send_message(
                chat_id=user_id,
                text=status_text,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка при выполнении /status: {e}")
    
    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /mute."""
        # Проверяем, включена ли функция мьюта
        if not self.bot.config.MUTE_ENABLED:
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
            await update.message.delete()
            
            # По умолчанию мьют из config
            mute_duration = self.bot.config.DEFAULT_MUTE_DURATION
            
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
                    mute_duration = 3600
            
            # Устанавливаем мьют
            mute_end_time = self.bot.get_current_time() + mute_duration
            self.bot.muted_users[user_id] = mute_end_time
            
            # Формируем время окончания
            from datetime import datetime
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
        """Обработчик команды /unmute."""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        logger.info(f"Получена команда /unmute от пользователя {user_id} ({user_name})")
        
        try:
            await update.message.delete()
            
            # Проверяем, замьючен ли пользователь
            if user_id in self.bot.muted_users and self.bot.muted_users[user_id] > self.bot.get_current_time():
                # Убираем мьют
                del self.bot.muted_users[user_id]
                
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
