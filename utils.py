"""Модуль для вспомогательных функций."""

import os
import json
import logging
import time

logger = logging.getLogger(__name__)


def get_current_time():
    """Возвращает текущее время в формате timestamp."""
    return time.time()


def load_subscribers(data_dir):
    """Загружает список подписчиков из файла.
    
    Args:
        data_dir: Директория для хранения данных
        
    Returns:
        set: Множество ID подписчиков
    """
    try:
        subscribers_file = os.path.join(data_dir, 'subscribers.json')
        if os.path.exists(subscribers_file):
            with open(subscribers_file, 'r', encoding='utf-8') as f:
                subscribers = json.load(f)
                logger.info(f"Загружено {len(subscribers)} подписчиков")
                return set(subscribers)
    except Exception as e:
        logger.error(f"Ошибка загрузки подписчиков: {e}")
    return set()


def save_subscribers(subscribers, data_dir):
    """Сохраняет список подписчиков в файл.
    
    Args:
        subscribers: Множество ID подписчиков
        data_dir: Директория для хранения данных
    """
    try:
        subscribers_file = os.path.join(data_dir, 'subscribers.json')
        with open(subscribers_file, 'w', encoding='utf-8') as f:
            json.dump(list(subscribers), f)
        logger.info(f"Сохранено {len(subscribers)} подписчиков")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписчиков: {e}")


def load_subscriber_activity(data_dir):
    """Загружает активность подписчиков из файла.
    
    Args:
        data_dir: Директория для хранения данных
        
    Returns:
        dict: Словарь активности подписчиков
    """
    try:
        activity_file = os.path.join(data_dir, 'subscriber_activity.json')
        if os.path.exists(activity_file):
            with open(activity_file, 'r', encoding='utf-8') as f:
                activity = json.load(f)
                logger.info(f"Загружена активность {len(activity)} подписчиков")
                return activity
    except Exception as e:
        logger.error(f"Ошибка загрузки активности подписчиков: {e}")
    return {}


def save_subscriber_activity(subscriber_activity, data_dir):
    """Сохраняет активность подписчиков в файл.
    
    Args:
        subscriber_activity: Словарь активности подписчиков
        data_dir: Директория для хранения данных
    """
    try:
        activity_file = os.path.join(data_dir, 'subscriber_activity.json')
        with open(activity_file, 'w', encoding='utf-8') as f:
            json.dump(subscriber_activity, f)
        logger.info(f"Сохранена активность {len(subscriber_activity)} подписчиков")
    except Exception as e:
        logger.error(f"Ошибка сохранения активности подписчиков: {e}")


def load_muted_users(data_dir):
    """Загружает список замьюченных пользователей из файла.
    
    Args:
        data_dir: Директория для хранения данных
        
    Returns:
        dict: Словарь замьюченных пользователей
    """
    try:
        muted_file = os.path.join(data_dir, 'muted_users.json')
        if os.path.exists(muted_file):
            with open(muted_file, 'r', encoding='utf-8') as f:
                muted_users = json.load(f)
                logger.info(f"Загружено {len(muted_users)} замьюченных пользователей")
                return muted_users
    except Exception as e:
        logger.error(f"Ошибка загрузки замьюченных пользователей: {e}")
    return {}


def save_muted_users(muted_users, data_dir):
    """Сохраняет список замьюченных пользователей в файл.
    
    Args:
        muted_users: Словарь замьюченных пользователей
        data_dir: Директория для хранения данных
    """
    try:
        muted_file = os.path.join(data_dir, 'muted_users.json')
        with open(muted_file, 'w', encoding='utf-8') as f:
            json.dump(muted_users, f)
        logger.info(f"Сохранено {len(muted_users)} замьюченных пользователей")
    except Exception as e:
        logger.error(f"Ошибка сохранения замьюченных пользователей: {e}")


def load_broadcast_templates(data_dir):
    """Загружает шаблоны рассылки из файла.
    
    Args:
        data_dir: Директория для хранения данных
        
    Returns:
        dict: Словарь шаблонов рассылки
    """
    try:
        templates_file = os.path.join(data_dir, 'broadcast_templates.json')
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                templates = json.load(f)
                logger.info(f"Загружено {len(templates)} шаблонов рассылки")
                return templates
    except Exception as e:
        logger.error(f"Ошибка загрузки шаблонов рассылки: {e}")
    return {}


def save_broadcast_templates(broadcast_templates, data_dir):
    """Сохраняет шаблоны рассылки в файл.
    
    Args:
        broadcast_templates: Словарь шаблонов рассылки
        data_dir: Директория для хранения данных
    """
    try:
        templates_file = os.path.join(data_dir, 'broadcast_templates.json')
        with open(templates_file, 'w', encoding='utf-8') as f:
            json.dump(broadcast_templates, f)
        logger.info(f"Сохранено {len(broadcast_templates)} шаблонов рассылки")
    except Exception as e:
        logger.error(f"Ошибка сохранения шаблонов рассылки: {e}")


def load_admin_log(data_dir):
    """Загружает лог действий админа из файла.
    
    Args:
        data_dir: Директория для хранения данных
        
    Returns:
        list: Список записей лога
    """
    try:
        log_file = os.path.join(data_dir, 'admin_log.json')
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log = json.load(f)
                logger.info(f"Загружено {len(log)} записей лога")
                return log
    except Exception as e:
        logger.error(f"Ошибка загрузки лога админа: {e}")
    return []


def save_admin_log(admin_log, data_dir):
    """Сохраняет лог действий админа в файл.
    
    Args:
        admin_log: Список записей лога
        data_dir: Директория для хранения данных
    """
    try:
        log_file = os.path.join(data_dir, 'admin_log.json')
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(admin_log, f)
        logger.info(f"Сохранено {len(admin_log)} записей лога")
    except Exception as e:
        logger.error(f"Ошибка сохранения лога админа: {e}")


def setup_logging(log_level):
    """Настраивает логирование.
    
    Args:
        log_level: Уровень логирования
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
