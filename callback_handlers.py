"""Модуль для обработчиков кнопок (callback queries)."""

import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Класс для обработчиков кнопок."""
    
    def __init__(self, bot):
        """Инициализация обработчиков кнопок.
        
        Args:
            bot: Экземпляр бота
        """
        self.bot = bot
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик всех кнопок."""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user_name = query.from_user.first_name or query.from_user.username
        
        logger.info(f"Нажата кнопка {query.data} пользователем {user_id} ({user_name})")
        
        try:
            # Подписка/отписка
            if query.data == "subscribe":
                await self.handle_subscribe(query, user_id)
            elif query.data == "unsubscribe":
                await self.handle_unsubscribe(query, user_id)
            
            # Админ панель
            elif query.data == "admin_stats":
                await self.handle_admin_stats(query, user_id)
            elif query.data == "admin_users":
                await self.handle_admin_users(query, user_id)
            elif query.data == "admin_activity":
                await self.handle_admin_activity(query, user_id)
            elif query.data == "admin_cleanup_inactive":
                await self.handle_admin_cleanup_inactive(query, user_id)
            elif query.data == "admin_subscribers_enabled":
                await self.handle_admin_subscribers_enabled(query, user_id)
            elif query.data == "admin_subscribers_disabled":
                await self.handle_admin_subscribers_disabled(query, user_id)
            elif query.data == "admin_unmute_all":
                await self.handle_admin_unmute_all(query, user_id)
            elif query.data == "admin_users_list":
                await self.handle_admin_users_list(query, user_id)
            elif query.data == "admin_muted_list":
                await self.handle_admin_muted_list(query, user_id)
            elif query.data == "admin_broadcast_menu":
                await self.handle_admin_broadcast_menu(query, user_id)
            elif query.data == "admin_broadcast_type_text":
                await self.handle_admin_broadcast_type_text(query, context)
            elif query.data == "admin_broadcast_type_html":
                await self.handle_admin_broadcast_type_html(query, context)
            elif query.data == "admin_clear_menu":
                await self.handle_admin_clear_menu(query, user_id)
            elif query.data.startswith("admin_clear_old_"):
                await self.handle_admin_clear_old(query, user_id, query.data)
            elif query.data == "admin_clearall_confirm":
                await self.handle_admin_clearall_confirm(query, user_id)
            elif query.data == "admin_clearall_do":
                await self.handle_admin_clearall_do(query, user_id)
            elif query.data == "admin_system":
                await self.handle_admin_system(query, user_id)
            elif query.data == "admin_restart_confirm":
                await self.handle_admin_restart_confirm(query, user_id)
            elif query.data == "admin_restart_do":
                await self.handle_admin_restart_do(query, user_id)
            elif query.data == "admin_back":
                await self.handle_admin_back(query, user_id)
            elif query.data == "admin_close":
                await self.handle_admin_close(query, user_id)
            elif query.data == "admin_broadcast":
                await self.handle_admin_broadcast(query, user_id)
            elif query.data == "admin_clearall":
                await self.handle_admin_clearall(query, user_id)
            elif query.data == "admin_restart":
                await self.handle_admin_restart(query, user_id)
            elif query.data == "admin_templates":
                await self.handle_admin_templates(query, user_id)
            elif query.data == "admin_template_add":
                await self.handle_admin_template_add(query, context)
            elif query.data == "admin_template_delete":
                await self.handle_admin_template_delete(query, user_id)
            elif query.data.startswith("admin_template_del_"):
                await self.handle_admin_template_del(query, user_id, query.data)
            elif query.data == "admin_log":
                await self.handle_admin_log(query, user_id)
            elif query.data == "admin_log_clear":
                await self.handle_admin_log_clear(query, user_id)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки {query.data}: {e}")
    
    async def handle_subscribe(self, query, user_id):
        """Обработчик кнопки подписки."""
        self.bot.subscribers.add(user_id)
        self.bot.save_subscribers()
        
        # Записываем активность подписчика
        self.bot.subscriber_activity[user_id] = {
            'subscribed_at': self.bot.get_current_time(),
            'messages_received': 0,
            'last_activity': self.bot.get_current_time()
        }
        
        # Редактируем сообщение
        keyboard = [[InlineKeyboardButton("\U0001F515 Отписаться", callback_data="unsubscribe")]]
        text = f"\U0001F514 Вы успешно подписались на уведомления от Discord-сервера '{self.bot.config.DISCORD_SERVER_NAME}'"
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Пользователь {user_id} подписался на уведомления")
    
    async def handle_unsubscribe(self, query, user_id):
        """Обработчик кнопки отписки."""
        self.bot.subscribers.discard(user_id)
        self.bot.save_subscribers()
        
        # Удаляем статистику подписчика
        if user_id in self.bot.subscriber_activity:
            del self.bot.subscriber_activity[user_id]
        
        # Редактируем сообщение
        keyboard = [[InlineKeyboardButton("\U0001F514 Подписаться", callback_data="subscribe")]]
        text = f"\U0001F515 Вы успешно отписались от уведомлений от Discord-сервера '{self.bot.config.DISCORD_SERVER_NAME}'"
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Пользователь {user_id} отписался от уведомлений")
    
    async def handle_admin_back(self, query, user_id):
        """Обработчик кнопки Назад."""
        # Рассчитываем статистику
        uptime = self.bot.get_current_time() - self.bot.start_time
        uptime_hours = int(uptime // 3600)
        uptime_minutes = int((uptime % 3600) // 60)
        muted_count = len([uid for uid, end_time in self.bot.muted_users.items() if end_time > self.bot.get_current_time()])
        
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
\U0001F465 Подписчиков: <i>{len(self.bot.subscribers)}</i>
\U0001F507 Замьючено: <i>{muted_count}</i>
\U0001F4E8 Сообщений: <i>{self.bot.message_count}</i>
\U000023F1 Время работы: <i>{uptime_hours}ч {uptime_minutes}м</i>

Выберите действие ниже:
        """
        
        await query.edit_message_text(
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def handle_admin_close(self, query, user_id):
        """Обработчик кнопки закрытия админ панели."""
        await query.edit_message_text(
            text="\U0000274C Админ панель закрыта",
            reply_markup=None
        )
    
    async def handle_admin_stats(self, query, user_id):
        """Обработчик кнопки статистики."""
        uptime = self.bot.get_current_time() - self.bot.start_time
        uptime_hours = int(uptime // 3600)
        uptime_minutes = int((uptime % 3600) // 60)
        muted_count = len([uid for uid, end_time in self.bot.muted_users.items() if end_time > self.bot.get_current_time()])
        
        stats_text = f"""
<b>\U0001F4CA Детальная статистика бота</b>

<b>\U0001F465 Пользователи:</b>
• Подписчиков: <i>{len(self.bot.subscribers)}</i>
• Замьючено: <i>{muted_count}</i>

<b>\U0001F4E8 Сообщения:</b>
• Переслано: <i>{self.bot.message_count}</i>
• Интервал проверки: <i>{self.bot.config.POLLING_INTERVAL} сек</i>

<b>\U000023F1 Время работы:</b>
• Запущен: <i>{datetime.fromtimestamp(self.bot.start_time).strftime('%d.%m.%Y %H:%M')}</i>
• Аптайм: <i>{uptime_hours}ч {uptime_minutes}м</i>

<b>\U0001F527 Настройки:</b>
• Батч размер: <i>{self.bot.config.BATCH_SIZE}</i>
• Макс. отправок: <i>{self.bot.config.MAX_CONCURRENT_SENDS}</i>
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
    
    async def handle_admin_users(self, query, user_id):
        """Обработчик кнопки управления пользователями."""
        users_text = f"""
<b>\U0001F465 Управление пользователями</b>

Всего подписчиков: <i>{len(self.bot.subscribers)}</i>
Замьючено: <i>{len([uid for uid, end_time in self.bot.muted_users.items() if end_time > self.bot.get_current_time()])}</i>

Выберите действие:
        """
        
        keyboard = [
            [InlineKeyboardButton("\U0001F4CB Подписчики с уведомлениями", callback_data="admin_subscribers_enabled")],
            [InlineKeyboardButton("\U0001F507 Подписчики без уведомлений", callback_data="admin_subscribers_disabled")],
            [InlineKeyboardButton(" Активность подписчиков", callback_data="admin_activity")],
            [InlineKeyboardButton("\U0001F9F9 Очистить неактивных (30дней)", callback_data="admin_cleanup_inactive")],
            [InlineKeyboardButton(" Размьютить всех", callback_data="admin_unmute_all")],
            [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            text=users_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    async def handle_admin_activity(self, query, user_id):
        """Обработчик кнопки активности подписчиков."""
        activity_text = "<b>\U0001F4CA Активность подписчиков</b>\n\n"
        
        if self.bot.subscriber_activity:
            sorted_activity = sorted(
                self.bot.subscriber_activity.items(),
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
    
    async def handle_admin_cleanup_inactive(self, query, user_id):
        """Обработчик очистки неактивных подписчиков."""
        current_time = self.bot.get_current_time()
        thirty_days_ago = current_time - (30 * 24 * 3600)
        
        inactive_users = [
            uid for uid, data in self.bot.subscriber_activity.items()
            if data['last_activity'] < thirty_days_ago
        ]
        
        if inactive_users:
            for uid in inactive_users:
                self.bot.subscribers.discard(uid)
                if uid in self.bot.subscriber_activity:
                    del self.bot.subscriber_activity[uid]
            
            self.bot.save_subscribers()
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
    
    async def handle_admin_subscribers_enabled(self, query, user_id):
        """Обработчик списка подписчиков с включенными уведомлениями."""
        current_time = self.bot.get_current_time()
        enabled_users = [uid for uid in self.bot.subscribers if uid not in self.bot.muted_users or self.bot.muted_users[uid] < current_time]
        
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
    
    async def handle_admin_subscribers_disabled(self, query, user_id):
        """Обработчик списка подписчиков с выключенными уведомлениями."""
        current_time = self.bot.get_current_time()
        disabled_users = [uid for uid in self.bot.subscribers if uid in self.bot.muted_users and self.bot.muted_users[uid] > current_time]
        
        if disabled_users:
            list_text = f"<b>\U0001F507 Люди, у которых выключены уведомления</b>\n\n"
            for i, user_id in enumerate(disabled_users[:50], 1):
                mute_end = self.bot.muted_users[user_id]
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
    
    async def handle_admin_unmute_all(self, query, user_id):
        """Обработчик размьючения всех пользователей."""
        current_time = self.bot.get_current_time()
        muted_count = len([uid for uid, end_time in self.bot.muted_users.items() if end_time > current_time])
        
        if muted_count == 0:
            result_text = "\U0000274C Нет замьюченных пользователей"
        else:
            self.bot.muted_users.clear()
            result_text = f"\U00002705 Размьючено {muted_count} пользователей"
        
        keyboard = [
            [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_users")]
        ]
        
        await query.edit_message_text(
            text=result_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Администратор {user_id} размьючил всех пользователей")
    
    async def handle_admin_users_list(self, query, user_id):
        """Обработчик списка всех подписчиков."""
        subscribers_list = list(self.bot.subscribers)
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
    
    async def handle_admin_muted_list(self, query, user_id):
        """Обработчик списка замьюченных пользователей."""
        current_time = self.bot.get_current_time()
        muted_list = [(uid, end_time) for uid, end_time in self.bot.muted_users.items() if end_time > current_time]
        
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
    
    async def handle_admin_broadcast_menu(self, query, user_id):
        """Обработчик меню рассылки."""
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
    
    async def handle_admin_broadcast_type_text(self, query, context):
        """Обработчик выбора текстовой рассылки."""
        await query.edit_message_text(
            text="\U0001F4DD Введите текст для рассылки:\n\nОтправьте сообщение как обычный текст, и оно будет разослано всем подписчикам.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Отмена", callback_data="admin_back")]])
        )
        context.user_data['waiting_for_broadcast'] = 'text'
    
    async def handle_admin_broadcast_type_html(self, query, context):
        """Обработчик выбора HTML рассылки."""
        await query.edit_message_text(
            text="\U0001F3A8 Введите HTML текст для рассылки:\n\nОтправьте сообщение с HTML тегами, и оно будет разослано всем подписчикам.\nПример: <b>Жирный текст</b> и <i>курсив</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Отмена", callback_data="admin_back")]])
        )
        context.user_data['waiting_for_broadcast'] = 'html'
    
    async def handle_admin_clear_menu(self, query, user_id):
        """Обработчик меню очистки."""
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
    
    async def handle_admin_clear_old(self, query, user_id, callback_data):
        """Обработчик удаления старых сообщений."""
        hours = int(callback_data.split('_')[-1])
        
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
        
        result_text = f"\U00002705 Удалено {deleted_count} сообщений старше {hours} часов"
        
        keyboard = [
            [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_clear_menu")]
        ]
        
        await query.edit_message_text(
            text=result_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Администратор {user_id} удалил {deleted_count} сообщений старше {hours} часов через панель")
    
    async def handle_admin_clearall_confirm(self, query, user_id):
        """Обработчик подтверждения очистки всех чатов."""
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
    
    async def handle_admin_clearall_do(self, query, user_id):
        """Обработчик выполнения очистки всех чатов."""
        cleared_count = 0
        for subscriber_id in self.bot.subscribers:
            try:
                await self.bot.cleanup_chat_before_pinned(subscriber_id)
                cleared_count += 1
            except Exception as e:
                logger.error(f"Ошибка очистки чата пользователя {subscriber_id}: {e}")
        
        result_text = f"\U00002705 Очищено {cleared_count} из {len(self.bot.subscribers)} чатов"
        
        keyboard = [
            [InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            text=result_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"Администратор {user_id} очистил все чаты через панель")
    
    async def handle_admin_system(self, query, user_id):
        """Обработчик системных команд."""
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
    
    async def handle_admin_restart_confirm(self, query, user_id):
        """Обработчик подтверждения перезапуска."""
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
    
    async def handle_admin_restart_do(self, query, user_id):
        """Обработчик выполнения перезапуска."""
        await query.edit_message_text(
            text="🔄 Перезапуск бота...",
            reply_markup=None
        )
        
        logger.info(f"Администратор {user_id} перезапустил бота через панель")
        
        # Перезапуск бота
        import sys
        import os
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    async def handle_admin_broadcast(self, query, user_id):
        """Обработчик старого метода рассылки."""
        await query.edit_message_text(
            text="\U0001F4E2 Введите сообщение для рассылки:\nИспользуйте: /broadcast <текст>",
            reply_markup=None
        )
    
    async def handle_admin_clearall(self, query, user_id):
        """Обработчик старого метода очистки."""
        await query.edit_message_text(
            text="\U0001F5D1 Очистка всех чатов...\nИспользуйте: /clearall",
            reply_markup=None
        )
    
    async def handle_admin_restart(self, query, user_id):
        """Обработчик старого метода перезапуска."""
        await query.edit_message_text(
            text="\U0001F504 Перезапуск бота...\nИспользуйте: /restart",
            reply_markup=None
        )
    
    async def handle_admin_templates(self, query, user_id):
        """Обработчик управления шаблонами."""
        templates_text = "<b>\U0001F4DD Шаблоны рассылки</b>\n\n"
        
        if self.bot.broadcast_templates:
            for name, text in self.bot.broadcast_templates.items():
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
    
    async def handle_admin_template_add(self, query, context):
        """Обработчик добавления шаблона."""
        await query.edit_message_text(
            text="\U0001F4DD Введите название шаблона и текст через |:\n\nПример: Название|Текст шаблона",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Отмена", callback_data="admin_templates")]])
        )
        context.user_data['waiting_for_template'] = True
    
    async def handle_admin_template_delete(self, query, user_id):
        """Обработчик удаления шаблона."""
        if self.bot.broadcast_templates:
            delete_text = "<b>\U0001F5D1 Выберите шаблон для удаления:</b>\n\n"
            keyboard = []
            for name in self.bot.broadcast_templates.keys():
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
    
    async def handle_admin_template_del(self, query, user_id, callback_data):
        """Обработчик удаления конкретного шаблона."""
        template_name = callback_data.replace("admin_template_del_", "")
        if template_name in self.bot.broadcast_templates:
            del self.bot.broadcast_templates[template_name]
            result_text = f"\U00002705 Шаблон '{template_name}' удален"
        else:
            result_text = "\U0000274C Шаблон не найден"
        
        await query.edit_message_text(
            text=result_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_templates")]])
        )
    
    async def handle_admin_log(self, query, user_id):
        """Обработчик лога действий админа."""
        log_text = "<b>\U0001F4CB Лог действий админа</b>\n\n"
        
        if self.bot.admin_log:
            for log_entry in self.bot.admin_log[-20:]:
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
    
    async def handle_admin_log_clear(self, query, user_id):
        """Обработчик очистки лога."""
        self.bot.admin_log.clear()
        await query.edit_message_text(
            text="\U00002705 Лог очищен",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U00002B05 Назад", callback_data="admin_back")]])
        )
