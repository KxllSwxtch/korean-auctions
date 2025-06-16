#!/usr/bin/env python3
"""
Скрипт для запуска всех тестов Glovis
Комплексная проверка надежности системы
"""

import asyncio
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Dict, Any


class TestRunner:
    """Запускатель тестов"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.results = []

    def log(self, message: str, level: str = "INFO"):
        """Логирование с временной меткой"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_command(self, command: List[str], description: str) -> Dict[str, Any]:
        """Запуск команды и получение результата"""
        self.log(f"🚀 Запуск: {description}")
        start_time = time.time()

        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=300  # 5 минут таймаут
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            return {
                "test_name": description,
                "success": success,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "test_name": description,
                "success": False,
                "duration": duration,
                "stdout": "",
                "stderr": "Тест превысил таймаут (5 минут)",
                "return_code": -1,
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "test_name": description,
                "success": False,
                "duration": duration,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
            }

    def print_result(self, result: Dict[str, Any]):
        """Вывод результата теста"""
        status = "✅ ПРОЙДЕН" if result["success"] else "❌ ПРОВАЛЕН"
        self.log(f"{status} - {result['test_name']} ({result['duration']:.1f}с)")

        if not result["success"]:
            if result["stderr"]:
                self.log(f"   ❌ Ошибка: {result['stderr'][:200]}...")
            if result["return_code"] != 0:
                self.log(f"   📊 Код возврата: {result['return_code']}")

        print("-" * 60)

    def run_all_tests(self):
        """Запуск всех тестов"""
        self.log("🎯 ЗАПУСК КОМПЛЕКСНОГО ТЕСТИРОВАНИЯ GLOVIS")
        self.log("=" * 60)

        # Список тестов для запуска
        tests = [
            {
                "command": ["python", "test_glovis_session.py"],
                "description": "Базовые тесты сессии",
            },
            {
                "command": ["python", "stress_test_glovis.py", "--light"],
                "description": "Легкий стресс-тест",
            },
            {
                "command": ["python", "update_glovis_cookies.py", "--check-only"],
                "description": "Проверка cookies",
            },
            {
                "command": ["python", "monitor_glovis_session.py", "--interval", "1"],
                "description": "Быстрый мониторинг (10 секунд)",
                "timeout": 15,
            },
        ]

        # Запускаем тесты
        for test_config in tests:
            result = self.run_command(
                test_config["command"], test_config["description"]
            )

            self.results.append(result)
            self.print_result(result)

            # Пауза между тестами
            time.sleep(2)

        # Итоговый отчет
        self.print_summary()

    def print_summary(self):
        """Печать итогового отчета"""
        self.log("📊 ИТОГОВЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ")
        self.log("=" * 60)

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = total_tests - passed_tests
        total_duration = sum(r["duration"] for r in self.results)

        self.log(f"📈 Всего тестов: {total_tests}")
        self.log(f"✅ Пройдено: {passed_tests}")
        self.log(f"❌ Провалено: {failed_tests}")
        self.log(f"⏱️ Общее время: {total_duration:.1f}с")
        self.log(f"📊 Успешность: {(passed_tests/total_tests*100):.1f}%")

        if failed_tests > 0:
            self.log("\n❌ ПРОВАЛЕННЫЕ ТЕСТЫ:")
            for result in self.results:
                if not result["success"]:
                    self.log(f"   • {result['test_name']}")
                    if result["stderr"]:
                        self.log(f"     Ошибка: {result['stderr'][:100]}...")

        self.log("=" * 60)

        # Рекомендации
        if passed_tests == total_tests:
            self.log("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система готова к работе.")
            self.log("💡 Рекомендации:")
            self.log("   • Настройте автоматический мониторинг")
            self.log("   • Регулярно обновляйте cookies")
            self.log("   • Следите за логами в продакшене")
        elif passed_tests >= total_tests * 0.8:
            self.log("⚠️ Большинство тестов пройдено, но есть проблемы.")
            self.log("💡 Рекомендации:")
            self.log("   • Исправьте проваленные тесты")
            self.log("   • Проверьте конфигурацию")
            self.log("   • Убедитесь что API сервер запущен")
        else:
            self.log("🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ! Система требует доработки.")
            self.log("💡 Рекомендации:")
            self.log("   • Проверьте что API сервер запущен")
            self.log("   • Обновите cookies в glovis-curl-request.py")
            self.log("   • Проверьте сетевое подключение")
            self.log("   • Изучите логи ошибок")


def check_prerequisites():
    """Проверка предварительных условий"""
    print("🔍 Проверка предварительных условий...")

    # Проверяем наличие файлов
    required_files = [
        "test_glovis_session.py",
        "stress_test_glovis.py",
        "update_glovis_cookies.py",
        "monitor_glovis_session.py",
        "glovis-curl-request.py",
    ]

    missing_files = []
    for file in required_files:
        try:
            with open(file, "r"):
                pass
        except FileNotFoundError:
            missing_files.append(file)

    if missing_files:
        print(f"❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False

    # Проверяем доступность API
    import requests

    try:
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API сервер доступен")
        else:
            print(f"⚠️ API сервер вернул статус {response.status_code}")
    except Exception as e:
        print(f"❌ API сервер недоступен: {e}")
        print("💡 Убедитесь что сервер запущен: uvicorn app.main:app --reload")
        return False

    print("✅ Все предварительные условия выполнены")
    return True


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Запуск всех тестов Glovis")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="URL API сервера"
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Пропустить проверку предварительных условий",
    )
    parser.add_argument(
        "--quick", action="store_true", help="Быстрый режим (только основные тесты)"
    )

    args = parser.parse_args()

    print("🚀 КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ GLOVIS")
    print("=" * 50)

    # Проверяем предварительные условия
    if not args.skip_checks:
        if not check_prerequisites():
            print("\n❌ Тестирование прервано из-за неудовлетворенных условий")
            sys.exit(1)
        print()

    # Запускаем тесты
    runner = TestRunner(api_url=args.api_url)

    if args.quick:
        runner.log("⚡ Быстрый режим тестирования")
        # В быстром режиме запускаем только основные тесты
        quick_tests = [
            {
                "command": ["python", "update_glovis_cookies.py", "--check-only"],
                "description": "Проверка cookies и сессии",
            },
            {
                "command": ["python", "test_glovis_session.py"],
                "description": "Базовые тесты сессии",
            },
        ]

        for test_config in quick_tests:
            result = runner.run_command(
                test_config["command"], test_config["description"]
            )
            runner.results.append(result)
            runner.print_result(result)
    else:
        runner.run_all_tests()


if __name__ == "__main__":
    main()
