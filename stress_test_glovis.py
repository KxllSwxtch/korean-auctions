#!/usr/bin/env python3
"""
Стресс-тест для системы управления сессией Glovis
Проверяет стабильность под различными нагрузками
"""

import asyncio
import time
import requests
import random
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.glovis_service import GlovisService


@dataclass
class StressTestResult:
    """Результат стресс-теста"""

    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    min_response_time: float
    max_response_time: float
    errors: List[str]
    duration: float


class GlovisStressTester:
    """Стресс-тестер для Glovis"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.results = []
        self.lock = threading.Lock()

    def log(self, message: str, level: str = "INFO"):
        """Логирование с временной меткой"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}")

    async def single_request_test(self, request_id: int) -> Dict[str, Any]:
        """Выполнение одного запроса"""
        start_time = time.time()

        try:
            service = GlovisService()
            response = await service.get_car_list()
            duration = time.time() - start_time

            return {
                "request_id": request_id,
                "success": response.success,
                "duration": duration,
                "cars_count": len(response.cars) if response.cars else 0,
                "error": None if response.success else response.message,
            }

        except Exception as e:
            duration = time.time() - start_time
            return {
                "request_id": request_id,
                "success": False,
                "duration": duration,
                "cars_count": 0,
                "error": str(e),
            }

    def sync_request_test(self, request_id: int) -> Dict[str, Any]:
        """Синхронный запрос через HTTP API"""
        start_time = time.time()

        try:
            response = requests.get(f"{self.api_url}/api/v1/glovis/cars", timeout=30)
            duration = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                return {
                    "request_id": request_id,
                    "success": data.get("success", False),
                    "duration": duration,
                    "cars_count": len(data.get("data", {}).get("cars", [])),
                    "error": (
                        None
                        if data.get("success")
                        else data.get("message", "Unknown error")
                    ),
                }
            else:
                return {
                    "request_id": request_id,
                    "success": False,
                    "duration": duration,
                    "cars_count": 0,
                    "error": f"HTTP {response.status_code}: {response.text[:100]}",
                }

        except Exception as e:
            duration = time.time() - start_time
            return {
                "request_id": request_id,
                "success": False,
                "duration": duration,
                "cars_count": 0,
                "error": str(e),
            }

    async def concurrent_async_test(self, num_requests: int = 10) -> StressTestResult:
        """Тест параллельных асинхронных запросов"""
        self.log(
            f"🚀 Запуск теста параллельных async запросов ({num_requests} запросов)"
        )
        start_time = time.time()

        # Создаем задачи
        tasks = []
        for i in range(num_requests):
            task = self.single_request_test(i + 1)
            tasks.append(task)

        # Выполняем параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_duration = time.time() - start_time

        # Анализируем результаты
        successful_requests = 0
        failed_requests = 0
        response_times = []
        errors = []

        for result in results:
            if isinstance(result, Exception):
                failed_requests += 1
                errors.append(str(result))
            elif isinstance(result, dict):
                if result.get("success", False):
                    successful_requests += 1
                else:
                    failed_requests += 1
                    if result.get("error"):
                        errors.append(result["error"])

                response_times.append(result.get("duration", 0))

        return StressTestResult(
            test_name="concurrent_async",
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=(
                sum(response_times) / len(response_times) if response_times else 0
            ),
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            errors=errors[:10],  # Первые 10 ошибок
            duration=total_duration,
        )

    def concurrent_sync_test(self, num_requests: int = 10) -> StressTestResult:
        """Тест параллельных синхронных запросов через HTTP API"""
        self.log(
            f"🚀 Запуск теста параллельных HTTP запросов ({num_requests} запросов)"
        )
        start_time = time.time()

        # Используем ThreadPoolExecutor для параллельных HTTP запросов
        with ThreadPoolExecutor(max_workers=min(num_requests, 10)) as executor:
            futures = []
            for i in range(num_requests):
                future = executor.submit(self.sync_request_test, i + 1)
                futures.append(future)

            # Собираем результаты
            results = []
            for future in futures:
                try:
                    result = future.result(timeout=60)
                    results.append(result)
                except Exception as e:
                    results.append(
                        {
                            "request_id": -1,
                            "success": False,
                            "duration": 0,
                            "cars_count": 0,
                            "error": str(e),
                        }
                    )

        total_duration = time.time() - start_time

        # Анализируем результаты
        successful_requests = sum(1 for r in results if r.get("success", False))
        failed_requests = len(results) - successful_requests
        response_times = [r.get("duration", 0) for r in results]
        errors = [r.get("error") for r in results if r.get("error")]

        return StressTestResult(
            test_name="concurrent_sync",
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=(
                sum(response_times) / len(response_times) if response_times else 0
            ),
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            errors=errors[:10],
            duration=total_duration,
        )

    async def sequential_test(self, num_requests: int = 20) -> StressTestResult:
        """Тест последовательных запросов"""
        self.log(f"🚀 Запуск теста последовательных запросов ({num_requests} запросов)")
        start_time = time.time()

        results = []
        service = GlovisService()

        for i in range(num_requests):
            try:
                request_start = time.time()
                response = await service.get_car_list()
                request_duration = time.time() - request_start

                results.append(
                    {
                        "request_id": i + 1,
                        "success": response.success,
                        "duration": request_duration,
                        "cars_count": len(response.cars) if response.cars else 0,
                        "error": None if response.success else response.message,
                    }
                )

                # Небольшая пауза между запросами
                await asyncio.sleep(0.1)

            except Exception as e:
                request_duration = (
                    time.time() - request_start if "request_start" in locals() else 0
                )
                results.append(
                    {
                        "request_id": i + 1,
                        "success": False,
                        "duration": request_duration,
                        "cars_count": 0,
                        "error": str(e),
                    }
                )

        total_duration = time.time() - start_time

        # Анализируем результаты
        successful_requests = sum(1 for r in results if r.get("success", False))
        failed_requests = len(results) - successful_requests
        response_times = [r.get("duration", 0) for r in results]
        errors = [r.get("error") for r in results if r.get("error")]

        return StressTestResult(
            test_name="sequential",
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=(
                sum(response_times) / len(response_times) if response_times else 0
            ),
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            errors=errors[:10],
            duration=total_duration,
        )

    async def session_invalidation_test(self) -> StressTestResult:
        """Тест с принудительной инвалидацией сессии"""
        self.log("🚀 Запуск теста с инвалидацией сессии")
        start_time = time.time()

        results = []
        service = GlovisService()

        for i in range(10):
            try:
                # Каждый 3-й запрос инвалидируем сессию
                if i % 3 == 0 and i > 0:
                    self.log(f"   🔄 Инвалидация сессии на запросе {i + 1}")
                    service.refresh_session()

                request_start = time.time()
                response = await service.get_car_list()
                request_duration = time.time() - request_start

                results.append(
                    {
                        "request_id": i + 1,
                        "success": response.success,
                        "duration": request_duration,
                        "cars_count": len(response.cars) if response.cars else 0,
                        "error": None if response.success else response.message,
                        "session_invalidated": i % 3 == 0 and i > 0,
                    }
                )

            except Exception as e:
                request_duration = (
                    time.time() - request_start if "request_start" in locals() else 0
                )
                results.append(
                    {
                        "request_id": i + 1,
                        "success": False,
                        "duration": request_duration,
                        "cars_count": 0,
                        "error": str(e),
                        "session_invalidated": i % 3 == 0 and i > 0,
                    }
                )

        total_duration = time.time() - start_time

        # Анализируем результаты
        successful_requests = sum(1 for r in results if r.get("success", False))
        failed_requests = len(results) - successful_requests
        response_times = [r.get("duration", 0) for r in results]
        errors = [r.get("error") for r in results if r.get("error")]

        return StressTestResult(
            test_name="session_invalidation",
            total_requests=len(results),
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=(
                sum(response_times) / len(response_times) if response_times else 0
            ),
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            errors=errors,
            duration=total_duration,
        )

    def print_result(self, result: StressTestResult):
        """Печать результата теста"""
        success_rate = (
            (result.successful_requests / result.total_requests * 100)
            if result.total_requests > 0
            else 0
        )

        self.log(f"📊 Результаты теста '{result.test_name}':")
        self.log(f"   📈 Всего запросов: {result.total_requests}")
        self.log(f"   ✅ Успешных: {result.successful_requests}")
        self.log(f"   ❌ Неуспешных: {result.failed_requests}")
        self.log(f"   📊 Успешность: {success_rate:.1f}%")
        self.log(f"   ⏱️ Общее время: {result.duration:.2f}с")
        self.log(f"   ⚡ Среднее время ответа: {result.average_response_time:.3f}с")
        self.log(f"   🚀 Мин. время ответа: {result.min_response_time:.3f}с")
        self.log(f"   🐌 Макс. время ответа: {result.max_response_time:.3f}с")

        if result.errors:
            self.log(f"   ⚠️ Примеры ошибок:")
            for error in result.errors[:3]:  # Показываем первые 3 ошибки
                self.log(f"      • {error}")

        self.log("-" * 60)

    async def run_all_stress_tests(self):
        """Запуск всех стресс-тестов"""
        self.log("🚀 ЗАПУСК СТРЕСС-ТЕСТИРОВАНИЯ GLOVIS")
        self.log("=" * 60)

        tests = [
            ("Последовательные запросы", self.sequential_test(15)),
            ("Параллельные async запросы (5)", self.concurrent_async_test(5)),
            ("Параллельные async запросы (10)", self.concurrent_async_test(10)),
            ("Параллельные HTTP запросы (5)", None),  # Будет выполнен синхронно
            ("Инвалидация сессии", self.session_invalidation_test()),
        ]

        results = []

        for test_name, test_coro in tests:
            self.log(f"🧪 Выполняется: {test_name}")

            try:
                if test_coro is None:
                    # Синхронный тест
                    if "HTTP" in test_name:
                        result = self.concurrent_sync_test(5)
                else:
                    # Асинхронный тест
                    result = await test_coro

                results.append(result)
                self.print_result(result)

            except Exception as e:
                self.log(f"❌ Ошибка в тесте '{test_name}': {str(e)}")
                continue

            # Пауза между тестами
            await asyncio.sleep(2)

        # Итоговый отчет
        self.print_summary(results)

        return results

    def print_summary(self, results: List[StressTestResult]):
        """Печать итогового отчета"""
        self.log("📊 ИТОГОВЫЙ ОТЧЕТ СТРЕСС-ТЕСТИРОВАНИЯ")
        self.log("=" * 60)

        total_requests = sum(r.total_requests for r in results)
        total_successful = sum(r.successful_requests for r in results)
        total_failed = sum(r.failed_requests for r in results)
        overall_success_rate = (
            (total_successful / total_requests * 100) if total_requests > 0 else 0
        )

        self.log(f"📈 Общая статистика:")
        self.log(f"   🧪 Тестов выполнено: {len(results)}")
        self.log(f"   📊 Всего запросов: {total_requests}")
        self.log(f"   ✅ Успешных запросов: {total_successful}")
        self.log(f"   ❌ Неуспешных запросов: {total_failed}")
        self.log(f"   📊 Общая успешность: {overall_success_rate:.1f}%")

        # Анализ производительности
        avg_response_times = [
            r.average_response_time for r in results if r.average_response_time > 0
        ]
        if avg_response_times:
            self.log(
                f"   ⚡ Средняя скорость ответа: {sum(avg_response_times)/len(avg_response_times):.3f}с"
            )

        self.log("\n📋 Детали по тестам:")
        for result in results:
            success_rate = (
                (result.successful_requests / result.total_requests * 100)
                if result.total_requests > 0
                else 0
            )
            status = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 60 else "❌"
            self.log(
                f"   {status} {result.test_name}: {success_rate:.1f}% ({result.successful_requests}/{result.total_requests})"
            )

        # Рекомендации
        self.log("\n🎯 РЕКОМЕНДАЦИИ:")
        if overall_success_rate >= 90:
            self.log("   🎉 Отличная стабильность! Система готова к продакшену.")
        elif overall_success_rate >= 80:
            self.log("   ✅ Хорошая стабильность, но есть место для улучшений.")
        elif overall_success_rate >= 60:
            self.log("   ⚠️ Средняя стабильность. Рекомендуется оптимизация.")
        else:
            self.log("   🚨 Низкая стабильность! Требуется серьезная доработка.")

        self.log("=" * 60)


async def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Стресс-тестирование Glovis")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="URL API сервера"
    )
    parser.add_argument(
        "--light",
        action="store_true",
        help="Легкий режим тестирования (меньше запросов)",
    )

    args = parser.parse_args()

    tester = GlovisStressTester(api_url=args.api_url)

    if args.light:
        tester.log("🔧 Режим легкого тестирования")
        # В легком режиме уменьшаем количество запросов
        results = []

        # Только основные тесты
        tests = [
            ("Последовательные запросы", tester.sequential_test(5)),
            ("Параллельные запросы", tester.concurrent_async_test(3)),
        ]

        for test_name, test_coro in tests:
            tester.log(f"🧪 Выполняется: {test_name}")
            try:
                result = await test_coro
                results.append(result)
                tester.print_result(result)
            except Exception as e:
                tester.log(f"❌ Ошибка: {str(e)}")

        tester.print_summary(results)
    else:
        await tester.run_all_stress_tests()


if __name__ == "__main__":
    asyncio.run(main())
