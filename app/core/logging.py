import os
from loguru import logger
from app.core.config import get_settings


def setup_logging():
    """Настройка логирования"""
    settings = get_settings()

    # Создаем директорию для логов если её нет
    log_dir = os.path.dirname(settings.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Удаляем стандартный обработчик
    logger.remove()

    # Консольный обработчик
    logger.add(
        sink=lambda message: print(message, end=""),
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # Файловый обработчик
    logger.add(
        sink=settings.log_file,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
    )

    logger.info("Логирование настроено")


def get_logger(name: str = None):
    """Получить логгер"""
    if name:
        return logger.bind(name=name)
    return logger
