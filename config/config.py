"""Модуль для загрузки и управления конфигурацией бота."""

import json
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    """Класс для управления конфигурацией бота."""
    
    def __init__(self):
        """Инициализация конфигурации."""
        load_dotenv()
        self.config = self.load_config()
        
        # Discord настройки
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_SERVER_ID = self.config['discord']['server_id']
        self.DISCORD_CHANNEL_ID = self.config['discord']['channel_id']
        self.DISCORD_SERVER_NAME = self.config['discord']['server_name']
        
        # Telegram настройки
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.ADMIN_ID = int(self.config['telegram']['admin_id'])
        
        # Настройки мониторинга
        self.POLLING_INTERVAL = self.config['monitoring']['polling_interval']
        self.MESSAGE_LIMIT = self.config['monitoring']['message_limit']
        self.ENABLE_LOGGING = self.config['monitoring']['enable_logging']
        self.LOG_LEVEL = self.config['monitoring']['log_level']
        
        # Настройки производительности
        self.BATCH_SIZE = self.config['performance']['batch_size']
        self.BATCH_DELAY = self.config['performance']['batch_delay']
        self.MAX_CONCURRENT_SENDS = self.config['performance']['max_concurrent_sends']
        
        # Настройки функций
        self.MUTE_ENABLED = self.config['features']['mute_enabled']
        self.DEFAULT_MUTE_DURATION = self.config['features']['default_mute_duration']
        self.SUBSCRIPTIONS_ENABLED = self.config['features']['subscriptions_enabled']
        self.ATTACHMENTS_ENABLED = self.config['features']['attachments_enabled']
        self.AUTO_DELETE_ENABLED = self.config['features']['auto_delete_enabled']
        self.AUTO_DELETE_HOURS = self.config['features']['auto_delete_hours']
        
        # OpenAI настройки
        self.OPENAI_COMPATIBLE = self.config.get('openai_compatible', {})
        
        # Discord API заголовки
        self.headers = {
            'Authorization': f'{self.DISCORD_TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Connection': 'keep-alive'
        }
    
    def load_config(self):
        """Загружает конфигурацию из config.json."""
        try:
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
