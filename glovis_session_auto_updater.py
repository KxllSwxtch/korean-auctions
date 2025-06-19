#!/usr/bin/env python3
"""
Автоматический мониторинг и обновление Glovis сессии

Этот скрипт:
1. Проверяет статус Glovis сессии
2. Автоматически обновляет cookies при проблемах
3. Может работать как демон для непрерывного мониторинга
"""

import asyncio
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(
    "logs/glovis_session_updater.log",
    rotation="1 day",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",
)
logger.add(
    lambda msg: print(msg, end=""),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    level="INFO",
)


class GlovisSessionUpdater:
    """Автоматический обновлятор сессии Glovis"""

    def __init__(self):
        self.base_url = "https://auction.autobell.co.kr"
        self.check_interval = 300  # 5 минут
        self.session = requests.Session()

        # Настройка сессии
        self.session.verify = False
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        # Отключаем SSL warnings
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def load_cookies_from_curl_file(self) -> dict:
        """Загружает cookies из glovis-curl-request.py"""
        try:
            curl_file = Path("glovis-curl-request.py")
            if not curl_file.exists():
                logger.error("❌ Файл glovis-curl-request.py не найден")
                return {}

            # Читаем файл и извлекаем cookies
            with open(curl_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Находим определение cookies
            import re

            cookies_match = re.search(r"cookies = \{([^}]+)\}", content, re.DOTALL)
            if not cookies_match:
                logger.error("❌ Не найдено определение cookies в файле")
                return {}

            # Выполняем код для получения cookies
            cookies_code = f"cookies = {{{cookies_match.group(1)}}}"
            exec_globals = {}
            exec(cookies_code, exec_globals)

            cookies = exec_globals.get("cookies", {})
            logger.info(f"✅ Загружено {len(cookies)} cookies из curl файла")
            return cookies

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки cookies: {e}")
            return {}

    def check_session_health(self) -> dict:
        """Проверяет здоровье сессии"""
        try:
            # Пытаемся получить страницу аукциона
            url = f"{self.base_url}/auction/exhibitList.do"
            params = {"atn": "946", "acc": "20", "flag": "Y"}

            response = self.session.get(url, params=params, timeout=15)

            # Проверяем на редирект в логин
            if "<script>location.href='/login.do';</script>" in response.text:
                return {
                    "healthy": False,
                    "issue": "JavaScript редирект на логин",
                    "status_code": response.status_code,
                }

            # Проверяем статус код
            if response.status_code != 200:
                return {
                    "healthy": False,
                    "issue": f"HTTP ошибка {response.status_code}",
                    "status_code": response.status_code,
                }

            # Проверяем наличие ключевых элементов
            if "exhibitListInclude.do" not in response.text:
                return {
                    "healthy": False,
                    "issue": "Отсутствуют ключевые элементы страницы",
                    "status_code": response.status_code,
                }

            return {
                "healthy": True,
                "status_code": response.status_code,
                "response_size": len(response.text),
            }

        except Exception as e:
            return {
                "healthy": False,
                "issue": f"Ошибка запроса: {str(e)}",
                "status_code": None,
            }

    def update_session_cookies(self) -> bool:
        """Обновляет cookies сессии"""
        try:
            cookies = self.load_cookies_from_curl_file()
            if not cookies:
                return False

            # Обновляем cookies в сессии
            self.session.cookies.clear()
            for name, value in cookies.items():
                self.session.cookies.set(name, value)

            logger.info("🔄 Cookies обновлены в сессии")

            # Сохраняем в кэш для основного приложения
            cache_dir = Path("cache/sessions")
            cache_dir.mkdir(parents=True, exist_ok=True)

            cache_file = cache_dir / "glovis_session.json"
            session_data = {
                "cookies": cookies,
                "updated_at": datetime.now().isoformat(),
                "source": "auto_updater",
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            logger.info("💾 Cookies сохранены в кэш")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка обновления cookies: {e}")
            return False

    async def monitor_session(self, continuous: bool = False):
        """Мониторинг сессии"""
        logger.info("🔍 Начинаю мониторинг сессии Glovis")

        while True:
            try:
                # Проверяем здоровье сессии
                health = self.check_session_health()

                if health["healthy"]:
                    logger.info(f"✅ Сессия здорова (статус: {health['status_code']})")
                else:
                    logger.warning(f"⚠️ Проблема с сессией: {health['issue']}")

                    # Пытаемся восстановить
                    logger.info("🔄 Пытаюсь восстановить сессию...")
                    if self.update_session_cookies():
                        # Повторная проверка
                        await asyncio.sleep(5)
                        health_after = self.check_session_health()

                        if health_after["healthy"]:
                            logger.success("✅ Сессия успешно восстановлена!")
                        else:
                            logger.error(
                                f"❌ Восстановление не удалось: {health_after['issue']}"
                            )
                    else:
                        logger.error("❌ Не удалось обновить cookies")

                if not continuous:
                    break

                # Ждем до следующей проверки
                logger.info(
                    f"⏰ Следующая проверка через {self.check_interval} секунд..."
                )
                await asyncio.sleep(self.check_interval)

            except KeyboardInterrupt:
                logger.info("🛑 Мониторинг остановлен пользователем")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга: {e}")
                if continuous:
                    await asyncio.sleep(60)  # Ждем минуту при ошибке
                else:
                    break

    def close(self):
        """Закрытие сессии"""
        if self.session:
            self.session.close()


async def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Мониторинг и обновление Glovis сессии"
    )
    parser.add_argument(
        "--continuous", "-c", action="store_true", help="Непрерывный мониторинг"
    )
    parser.add_argument(
        "--interval", "-i", type=int, default=300, help="Интервал проверки в секундах"
    )

    args = parser.parse_args()

    updater = GlovisSessionUpdater()
    updater.check_interval = args.interval

    try:
        await updater.monitor_session(continuous=args.continuous)
    finally:
        updater.close()


if __name__ == "__main__":
    asyncio.run(main())
