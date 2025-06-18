#!/usr/bin/env python3
"""
Windows Service для автоматического отслеживания и обновления cookies Glovis
Отслеживает изменения в файле glovis-curl-request.py
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("glovis_watcher.log"), logging.StreamHandler()],
)
logger = logging.getLogger("GlovisWatcher")


class CurlFileHandler(FileSystemEventHandler):
    """Обработчик изменений файла с curl запросом"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.last_update = None
        self.update_cooldown = 10  # секунд между обновлениями

    def on_modified(self, event):
        """Обработка изменения файла"""
        if event.is_directory:
            return

        if event.src_path.endswith("glovis-curl-request.py"):
            logger.info(f"🔄 Обнаружено изменение в {event.src_path}")

            # Проверяем cooldown
            if self.last_update:
                elapsed = (datetime.now() - self.last_update).total_seconds()
                if elapsed < self.update_cooldown:
                    logger.info(
                        f"⏳ Ждем cooldown ({self.update_cooldown - elapsed:.1f}s)"
                    )
                    return

            # Обновляем cookies
            self.update_cookies_from_file(event.src_path)
            self.last_update = datetime.now()

    def update_cookies_from_file(self, file_path: str):
        """Извлекает и обновляет cookies из файла"""
        try:
            # Импортируем утилиту
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from app.utils.glovis_cookies_updater import GlovisCookiesUpdater

            # Извлекаем cookies
            result = GlovisCookiesUpdater.update_cookies_from_curl_file(file_path)

            if not result["success"] or not result["cookies"]:
                logger.error(f"❌ Не удалось извлечь cookies: {result['message']}")
                return

            logger.info(f"✅ Извлечено {len(result['cookies'])} cookies")

            # Отправляем на API
            response = requests.post(
                f"{self.api_url}/api/v1/glovis/update-cookies",
                json=result["cookies"],
                timeout=30,
            )

            if response.status_code == 200:
                api_result = response.json()
                if api_result.get("success"):
                    logger.info("✅ Cookies успешно обновлены через API")

                    # Проверяем статус новой сессии
                    session_data = api_result.get("data", {})
                    session_status = session_data.get("new_session_status", {})

                    if session_status.get("is_valid"):
                        logger.info("✅ Новая сессия валидна")
                    else:
                        logger.warning("⚠️ Проблемы с новой сессией:")
                        for issue in session_status.get("issues", []):
                            logger.warning(f"   - {issue}")
                else:
                    logger.error(f"❌ API ошибка: {api_result.get('message')}")
            else:
                logger.error(f"❌ HTTP ошибка: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении cookies: {e}")


class GlovisSessionWatcher:
    """Основной класс для отслеживания сессии Glovis"""

    def __init__(
        self,
        watch_file: str = "glovis-curl-request.py",
        api_url: str = "http://localhost:8000",
    ):
        self.watch_file = Path(watch_file)
        self.api_url = api_url
        self.observer = Observer()
        self.handler = CurlFileHandler(api_url)

    def start(self):
        """Запускает отслеживание"""
        if not self.watch_file.exists():
            logger.warning(f"⚠️ Файл {self.watch_file} не найден")

        # Настраиваем наблюдателя
        watch_dir = self.watch_file.parent
        self.observer.schedule(self.handler, str(watch_dir), recursive=False)

        logger.info(f"🚀 Запускаю отслеживание {self.watch_file}")
        logger.info(f"📁 Директория: {watch_dir}")
        logger.info(f"🌐 API URL: {self.api_url}")

        # Запускаем наблюдатель
        self.observer.start()

        try:
            while True:
                time.sleep(1)

                # Периодическая проверка статуса API
                if int(time.time()) % 300 == 0:  # Каждые 5 минут
                    self.check_api_status()

        except KeyboardInterrupt:
            logger.info("⏹️ Остановка по запросу пользователя")
            self.observer.stop()

        self.observer.join()

    def check_api_status(self):
        """Проверяет статус API"""
        try:
            response = requests.get(
                f"{self.api_url}/api/v1/glovis/check-session", timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    session_data = result.get("data", {})
                    is_valid = session_data.get("is_valid", False)
                    is_fresh = session_data.get("is_fresh", False)

                    status = "✅ валидна" if is_valid else "❌ невалидна"
                    freshness = "свежая" if is_fresh else "устаревшая"

                    logger.info(f"📊 Статус сессии: {status}, {freshness}")

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке статуса API: {e}")


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Windows Service для отслеживания cookies Glovis"
    )
    parser.add_argument(
        "--file",
        default="glovis-curl-request.py",
        help="Файл для отслеживания (по умолчанию: glovis-curl-request.py)",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="URL API сервера (по умолчанию: http://localhost:8000)",
    )

    args = parser.parse_args()

    # Создаем и запускаем watcher
    watcher = GlovisSessionWatcher(args.file, args.api_url)

    try:
        watcher.start()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
