"""Модуль для работы с Discord API."""

import requests
from requests.exceptions import SSLError, Timeout, RequestException
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class DiscordAPI:
    """Класс для работы с Discord API."""
    
    def __init__(self, config):
        """Инициализация Discord API клиента.
        
        Args:
            config: Объект конфигурации бота
        """
        self.config = config
        self.headers = config.headers
        self.channel_id = config.DISCORD_CHANNEL_ID
        self.message_limit = config.MESSAGE_LIMIT
    
    def get_messages(self):
        """Получает последние сообщения из Discord канала с retry механизмом.
        
        Returns:
            list: Список сообщений из Discord
        """
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                url = f"https://discord.com/api/v9/channels/{self.channel_id}/messages?limit={self.message_limit}"
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
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error("Не удалось преодолеть SSL ошибку после всех попыток")
                    return []
            except Timeout:
                logger.warning(f"Таймаут при запросе к Discord API (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    import time
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
    
    def format_message(self, message):
        """Форматирует сообщение из Discord для отправки в Telegram.
        
        Args:
            message: Сообщение из Discord
            
        Returns:
            tuple: (formatted_text, author_display_name, msk_time)
        """
        # Получаем время сообщения в МСК (UTC+3)
        timestamp = message.get('timestamp', '')
        utc_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        msk_timezone = timezone(timedelta(hours=3))
        msk_time = utc_time.astimezone(msk_timezone).strftime("%H:%M:%S %d.%m.%Y")
        
        # Получаем информацию об авторе
        author = message.get('author', {})
        author_name = author.get('username', 'Unknown')
        
        # Пытаемся получить ник с сервера
        member_data = message.get('member', {})
        server_nick = member_data.get('nick')
        
        # Для сервера 1506228881902801027 всегда используем серверный никнейм
        if self.config.DISCORD_SERVER_ID == '1506228881902801027' and server_nick:
            author_display_name = server_nick
        else:
            # Приоритет: серверный ник > global_name > username
            author_display_name = server_nick if server_nick else author.get('global_name', author_name)
        
        # Получаем контент сообщения и убираем пинги ролей
        import re
        content = message.get('content', '')
        content = re.sub(r'<@&\d+>', '', content)
        content = content.lstrip('>')
        if content.endswith('""'):
            content = content[:-2]
        content = content.strip()
        
        return content, author_display_name, msk_time
    
    def get_attachments(self, message):
        """Получает информацию о вложениях сообщения.
        
        Args:
            message: Сообщение из Discord
            
        Returns:
            list: Список URL вложений
        """
        attachments = message.get('attachments', [])
        return [attachment.get('url', 'No URL') for attachment in attachments]
