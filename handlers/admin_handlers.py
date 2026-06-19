"""Модуль для админ команд."""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class AdminHandlers:
    """Класс для обработчиков админ команд."""
    
    def __init__(self, bot):
        """Инициализация админ обработчиков.
        
        Args:
            bot: Экземпляр бота
        """
        self.bot = bot
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats (только для администратора)."""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            logger.warning(f"Пользователь {user_id} ({user_name}) пытался получить доступ к /stats")
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        logger.info(f"Получена команда /stats от администратора {user_id} ({user_name})")
        
        try:
            await update.message.delete()
            
            # Рассчитываем время работы
            uptime = self.bot.get_current_time() - self.bot.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            
            # Количество замьюченных пользователей
            muted_count = len([uid for uid, end_time in self.bot.muted_users.items() if end_time > self.bot.get_current_time()])
            
            # Формируем статистику
            stats_message = f"""
📊 Статистика бота

👥 Подписчики: {len(self.bot.subscribers)}
🔇 Замьюченные: {muted_count}
📨 Сообщений переслано: {self.bot.message_count}
⏰ Время работы: {uptime_hours}ч {uptime_minutes}м
📅 Запущен: {datetime.fromtimestamp(self.bot.start_time).strftime('%d.%m.%Y %H:%M')}

Сервер Discord: {self.bot.config.DISCORD_SERVER_NAME}
            """
            
            await context.bot.send_message(
                chat_id=user_id,
                text=stats_message
            )
            
            logger.info(f"Отправлена статистика администратору {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /stats: {e}")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /admin - админ панель."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            logger.warning(f"Пользователь {user_id} пытался получить доступ к админ панели")
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к админ панели!"
            )
            return
        
        logger.info(f"Администратор {user_id} открыл админ панель")
        
        try:
            await update.message.delete()
            
            # Рассчитываем статистику
            uptime = self.bot.get_current_time() - self.bot.start_time
            uptime_hours = int(uptime // 3600)
            uptime_minutes = int((uptime % 3600) // 60)
            muted_count = len([uid for uid, end_time in self.bot.muted_users.items() if end_time > self.bot.get_current_time()])
            
            # Создаем клавиатуру админ панели с категориями
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton("Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("\U0001F465 Управление пользователями", callback_data="admin_users")],
                [InlineKeyboardButton("Рассылка", callback_data="admin_broadcast_menu")],
                [InlineKeyboardButton("\U0001F5D1 Очистка чатов", callback_data="admin_clear_menu")],
                [InlineKeyboardButton("\U00002699 Системные команды", callback_data="admin_system")],
                [InlineKeyboardButton("\U0000274C Закрыть", callback_data="admin_close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            admin_text = f"""
<b>\U0001F6E0 Админ панель - Belomor Bot</b>

<b>Быстрая статистика:</b>
\U0001F465 Подписчиков: <i>{len(self.bot.subscribers)}</i>
\U0001F507Замьючено: <i>{muted_count}</i>
\U0001F4E8 Сообщений: <i>{self.bot.message_count}</i>
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
            logger.error(f"Ошибка при открытии админ панели: {e}")
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /broadcast - рассылка текстового сообщения."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        if not context.args:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="Использование: /broadcast <текст>"
            )
            return
        
        message_text = ' '.join(context.args)
        
        try:
            await update.message.delete()
            
            success_count = 0
            for subscriber_id in self.bot.subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=subscriber_id,
                        text=message_text
                    )
                    success_count += 1
                    import asyncio
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {subscriber_id}: {e}")
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 Сообщение отправлено {success_count} из {len(self.bot.subscribers)} подписчикам"
            )
            
            logger.info(f"Администратор {user_id} отправил рассылку: {message_text}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /broadcast: {e}")
    
    async def broadcast_html_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /broadcast_html - рассылка HTML сообщения."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        if not context.args:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="Использование: /broadcast_html <HTML текст>"
            )
            return
        
        message_text = ' '.join(context.args)
        
        try:
            await update.message.delete()
            
            success_count = 0
            for subscriber_id in self.bot.subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=subscriber_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    success_count += 1
                    import asyncio
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {subscriber_id}: {e}")
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U00002705 HTML сообщение отправлено {success_count} из {len(self.bot.subscribers)} подписчикам"
            )
            
            logger.info(f"Администратор {user_id} отправил HTML рассылку: {message_text}")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке /broadcast_html: {e}")
    
    async def clear_old_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clear_old - удаление сообщений старше N часов."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
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
        current_time = self.bot.get_current_time()
        delete_threshold = hours * 3600
        deleted_count = 0
        
        for (chat_id, message_id), sent_time in list(self.bot.sent_messages.items()):
            if current_time - sent_time > delete_threshold:
                try:
                    await self.bot.telegram_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    del self.bot.sent_messages[(chat_id, message_id)]
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
                    if (chat_id, message_id) in self.bot.sent_messages:
                        del self.bot.sent_messages[(chat_id, message_id)]
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"\U00002705 Удалено {deleted_count} сообщений старше {hours} часов"
        )
        
        logger.info(f"Администратор {user_id} удалил {deleted_count} сообщений старше {hours} часов")
    
    async def mute_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /mute_user - замьютить конкретного пользователя."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        if len(context.args) < 2:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="Использование: /mute_user <user_id> <часы>\nПример: /mute_user 123456789 24"
            )
            return
        
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
        target_user_id = context.args[0]
        mute_end_time = self.bot.get_current_time() + (hours * 3600)
        self.bot.muted_users[int(target_user_id)] = mute_end_time
        
        end_time_str = datetime.fromtimestamp(mute_end_time).strftime('%d.%m.%Y %H:%M')
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"\U00002705 Пользователь {target_user_id} замьючен до {end_time_str}"
        )
        
        logger.info(f"Администратор {user_id} замьючил пользователя {target_user_id} на {hours} часов")
    
    async def unmute_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /unmute_user - размьютить конкретного пользователя."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        if not context.args:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="Использование: /unmute_user <user_id>"
            )
            return
        
        target_user_id = context.args[0]
        await update.message.delete()
        
        # Убираем мьют
        if int(target_user_id) in self.bot.muted_users:
            del self.bot.muted_users[int(target_user_id)]
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
    
    async def clearall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clearall - очистка всех чатов."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        cleared_count = 0
        for subscriber_id in self.bot.subscribers:
            try:
                await self.bot.cleanup_chat_before_pinned(subscriber_id)
                cleared_count += 1
            except Exception as e:
                logger.error(f"Ошибка очистки чата пользователя {subscriber_id}: {e}")
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"\U00002705 Очищено {cleared_count} из {len(self.bot.subscribers)} чатов"
        )
        
        logger.info(f"Администратор {user_id} очистил все чаты")
    
    async def restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /restart - перезапуск бота."""
        user_id = update.effective_user.id
        
        # Проверяем, что это администратор
        if user_id != self.bot.config.ADMIN_ID:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 У вас нет доступа к этой команде!"
            )
            return
        
        await update.message.delete()
        await context.bot.send_message(
            chat_id=user_id,
            text="🔄 Перезапуск бота..."
        )
        
        logger.info(f"Администратор {user_id} инициировал перезапуск бота")
        
        # Перезапуск бота
        import sys
        import os
        os.execv(sys.executable, [sys.executable] + sys.argv)


