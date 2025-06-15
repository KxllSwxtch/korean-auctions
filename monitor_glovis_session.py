#!/usr/bin/env python3
"""
Скрипт для мониторинга сессии Glovis
Проверяет валидность JSESSIONID каждую минуту
"""

import asyncio
import time
import requests
from datetime import datetime
from typing import Dict, Any


class GlovisSessionMonitor:
    """Монитор сессии Glovis"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.check_interval = 60  # секунд
        self.session = requests.Session()

    def check_session_status(self) -> Dict[str, Any]:
        """Проверяет статус сессии через API"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/glovis/check-session", timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "message": response.text[:200],
                }

        except Exception as e:
            return {"success": False, "error": "Connection error", "message": str(e)}

    def refresh_session(self) -> Dict[str, Any]:
        """Обновляет сессию через API"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/glovis/refresh-session", timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "message": response.text[:200],
                }

        except Exception as e:
            return {"success": False, "error": "Connection error", "message": str(e)}

    def test_api_request(self) -> Dict[str, Any]:
        """Тестирует основной API запрос"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/glovis/cars?page=1", timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": data.get("success", False),
                    "cars_count": len(data.get("cars", [])),
                    "total_count": data.get("total_count", 0),
                    "message": data.get("message", ""),
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "message": response.text[:200],
                }

        except Exception as e:
            return {"success": False, "error": "Connection error", "message": str(e)}

    def print_status(self, session_check: Dict[str, Any], api_test: Dict[str, Any]):
        """Выводит статус в консоль"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{'='*60}")
        print(f"🕐 {timestamp} - МОНИТОРИНГ СЕССИИ GLOVIS")
        print(f"{'='*60}")

        # Статус сессии
        print("🔍 ПРОВЕРКА СЕССИИ:")
        if session_check.get("success", False):
            print("   ✅ Сессия валидна")
            data = session_check.get("data", {})
            print(f"   📊 Статус код: {data.get('status_code', 'N/A')}")
            print(f"   📁 Размер ответа: {data.get('response_size', 'N/A')} символов")

            # Информация о cookies
            cookies_info = data.get("cookies_info", {})
            if "JSESSIONID" in cookies_info:
                jsession = cookies_info["JSESSIONID"]
                print(f"   🍪 JSESSIONID: {jsession.get('value', 'N/A')}")
                print(f"   🌐 Домен: {jsession.get('domain', 'N/A')}")
        else:
            print("   ❌ Проблемы с сессией")
            issues = session_check.get("data", {}).get("issues", [])
            for issue in issues:
                print(f"   ⚠️  {issue}")

        # Тест API
        print("\n🚗 ТЕСТ API:")
        if api_test.get("success", False):
            print("   ✅ API работает корректно")
            print(f"   📊 Получено автомобилей: {api_test.get('cars_count', 0)}")
            print(f"   📊 Всего доступно: {api_test.get('total_count', 0)}")
        else:
            print("   ❌ Проблемы с API")
            print(f"   ⚠️  {api_test.get('message', 'Неизвестная ошибка')}")

        print(f"{'='*60}")

    def run_monitor(self):
        """Запускает мониторинг"""
        print("🚀 Запуск мониторинга сессии Glovis...")
        print(f"📍 URL: {self.base_url}")
        print(f"⏱️  Интервал проверки: {self.check_interval} секунд")
        print("🛑 Для остановки нажмите Ctrl+C")

        try:
            while True:
                # Проверяем сессию
                session_check = self.check_session_status()

                # Тестируем API
                api_test = self.test_api_request()

                # Выводим статус
                self.print_status(session_check, api_test)

                # Если сессия невалидна, пытаемся обновить
                if not session_check.get("success", False):
                    print("\n🔄 Попытка обновления сессии...")
                    refresh_result = self.refresh_session()

                    if refresh_result.get("success", False):
                        print("   ✅ Сессия успешно обновлена")
                    else:
                        print("   ❌ Не удалось обновить сессию")
                        print(
                            f"   ⚠️  {refresh_result.get('message', 'Неизвестная ошибка')}"
                        )

                # Ждем до следующей проверки
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            print("\n\n🛑 Мониторинг остановлен пользователем")
        except Exception as e:
            print(f"\n\n❌ Ошибка мониторинга: {e}")


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Мониторинг сессии Glovis")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="URL сервера API (по умолчанию: http://localhost:8000)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Интервал проверки в секундах (по умолчанию: 60)",
    )

    args = parser.parse_args()

    monitor = GlovisSessionMonitor(base_url=args.url)
    monitor.check_interval = args.interval
    monitor.run_monitor()


if __name__ == "__main__":
    main()
