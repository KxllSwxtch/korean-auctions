"""
Менеджер сессий для автоматического управления cookies аукционов
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
import threading
import requests
from app.core.logging import get_logger

logger = get_logger("session_manager")


class SessionManager:
    """Менеджер сессий для автоматического обновления cookies"""

    def __init__(self, cache_dir: str = "cache/sessions"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sessions = {}
        self._lock = threading.Lock()

    def save_session(
        self,
        service_name: str,
        cookies: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Сохраняет сессию в файл"""
        try:
            with self._lock:
                session_data = {
                    "cookies": cookies,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": metadata or {},
                }

                file_path = self.cache_dir / f"{service_name}_session.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(session_data, f, indent=2)

                self.sessions[service_name] = session_data
                logger.info(f"✅ Сессия {service_name} сохранена в {file_path}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении сессии {service_name}: {e}")
            return False

    def load_session(self, service_name: str) -> Optional[Dict[str, str]]:
        """Загружает сессию из файла"""
        try:
            file_path = self.cache_dir / f"{service_name}_session.json"

            if not file_path.exists():
                logger.warning(f"⚠️ Файл сессии {service_name} не найден")
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            # Проверяем возраст сессии
            timestamp = datetime.fromisoformat(session_data["timestamp"])
            age = datetime.now() - timestamp

            if age > timedelta(hours=24):
                logger.warning(f"⚠️ Сессия {service_name} старше 24 часов")

            self.sessions[service_name] = session_data
            return session_data["cookies"]

        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке сессии {service_name}: {e}")
            return None

    def get_session_age(self, service_name: str) -> Optional[timedelta]:
        """Возвращает возраст сессии"""
        try:
            if service_name in self.sessions:
                timestamp = datetime.fromisoformat(
                    self.sessions[service_name]["timestamp"]
                )
                return datetime.now() - timestamp

            file_path = self.cache_dir / f"{service_name}_session.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                timestamp = datetime.fromisoformat(session_data["timestamp"])
                return datetime.now() - timestamp

        except Exception:
            pass

        return None

    def is_session_fresh(self, service_name: str, max_age_hours: int = 12) -> bool:
        """Проверяет, свежая ли сессия"""
        age = self.get_session_age(service_name)
        if age is None:
            return False
        return age < timedelta(hours=max_age_hours)


class GlovisSessionMonitor:
    """Монитор сессии Glovis для автоматического обновления"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.monitoring = False
        self._monitor_thread = None
        self.check_interval = 300  # 5 минут

    def start_monitoring(self):
        """Запускает мониторинг сессии"""
        if self.monitoring:
            logger.warning("⚠️ Мониторинг уже запущен")
            return

        self.monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("🚀 Мониторинг сессии Glovis запущен")

    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        logger.info("🛑 Мониторинг сессии Glovis остановлен")

    def _monitor_loop(self):
        """Цикл мониторинга"""
        while self.monitoring:
            try:
                # Проверяем необходимость обновления
                if not self.session_manager.is_session_fresh("glovis", max_age_hours=6):
                    logger.info(
                        "🔄 Сессия Glovis устарела, пытаюсь обновить из файла..."
                    )
                    self._try_update_from_curl_file()

                # Ждем перед следующей проверкой
                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
                time.sleep(60)  # Подождем минуту при ошибке

    def _try_update_from_curl_file(self):
        """Пытается обновить сессию из файла curl"""
        curl_file = Path("glovis-curl-request.py")

        if not curl_file.exists():
            logger.warning("⚠️ Файл glovis-curl-request.py не найден")
            return

        # Проверяем, не слишком ли старый файл
        file_age = datetime.now() - datetime.fromtimestamp(curl_file.stat().st_mtime)
        if file_age > timedelta(hours=24):
            logger.warning(f"⚠️ Файл curl старше 24 часов ({file_age})")
            return

        try:
            # Используем утилиту для извлечения cookies
            from app.utils.glovis_cookies_updater import GlovisCookiesUpdater

            result = GlovisCookiesUpdater.update_cookies_from_curl_file(str(curl_file))

            if result["success"] and result["cookies"]:
                # Сохраняем новую сессию
                self.session_manager.save_session(
                    "glovis",
                    result["cookies"],
                    metadata={
                        "source": "curl_file",
                        "jsessionid": result.get("jsessionid"),
                    },
                )
                logger.info("✅ Сессия Glovis обновлена из файла curl")
            else:
                logger.error(f"❌ Не удалось извлечь cookies: {result['message']}")

        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении из curl файла: {e}")


# Глобальный экземпляр менеджера сессий
_session_manager = None
_glovis_monitor = None


def get_session_manager() -> SessionManager:
    """Получить глобальный экземпляр менеджера сессий"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def get_glovis_monitor() -> GlovisSessionMonitor:
    """Получить глобальный экземпляр монитора Glovis"""
    global _glovis_monitor
    if _glovis_monitor is None:
        _glovis_monitor = GlovisSessionMonitor(get_session_manager())
    return _glovis_monitor
