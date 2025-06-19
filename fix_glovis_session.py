#!/usr/bin/env python3
"""
Быстрое восстановление сессии Glovis
Скрипт автоматически восстанавливает сессию Glovis после выхода из приложения
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, Any


def check_api_status(api_url: str = "http://localhost:8000") -> bool:
    """Проверяет доступность API"""
    try:
        response = requests.get(f"{api_url}/docs", timeout=5)
        return response.status_code == 200
    except:
        return False


def check_current_session(api_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """Проверяет текущую сессию Glovis"""
    try:
        response = requests.get(f"{api_url}/api/v1/glovis/check-session", timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "data": {"is_valid": False, "issues": [f"HTTP {response.status_code}"]}
            }
    except Exception as e:
        return {"data": {"is_valid": False, "issues": [str(e)]}}


def test_car_list(api_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """Тестирует получение списка автомобилей"""
    try:
        response = requests.get(f"{api_url}/api/v1/glovis/cars?page=1", timeout=30)
        if response.status_code == 200:
            result = response.json()
            return {
                "success": result.get("success", False),
                "cars_count": (
                    len(result.get("cars", [])) if result.get("success") else 0
                ),
                "message": result.get("message", ""),
            }
        else:
            return {
                "success": False,
                "cars_count": 0,
                "message": f"HTTP {response.status_code}",
            }
    except Exception as e:
        return {"success": False, "cars_count": 0, "message": str(e)}


def run_auto_login(api_url: str = "http://localhost:8000") -> bool:
    """Запускает автоматический вход"""
    try:
        print("🔐 Запускаю автоматический вход...")
        import subprocess

        # Запускаем скрипт автоматического входа с обновлением API
        result = subprocess.run(
            ["python", "glovis_auto_login.py", "--api-url", api_url, "--update-api"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            print("✅ Автоматический вход выполнен успешно")
            return True
        else:
            print(f"❌ Ошибка автоматического входа:")
            print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("⏰ Timeout: Автоматический вход занял слишком много времени")
        return False
    except Exception as e:
        print(f"❌ Ошибка при запуске автоматического входа: {e}")
        return False


def main():
    """Основная функция восстановления сессии"""
    import argparse

    parser = argparse.ArgumentParser(description="Восстановление сессии Glovis")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="URL API сервера (по умолчанию: http://localhost:8000)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Принудительно перелогиниться даже если сессия валидна",
    )

    args = parser.parse_args()

    print("🚀 Восстановление сессии Glovis")
    print(f"🌐 API URL: {args.api_url}")
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Шаг 1: Проверяем доступность API
    print("1️⃣ Проверяю доступность API...")
    if not check_api_status(args.api_url):
        print("❌ API недоступно! Убедитесь что сервер запущен.")
        print("   Для запуска выполните: python main.py")
        return 1
    print("✅ API доступно")

    # Шаг 2: Проверяем текущую сессию
    print("\n2️⃣ Проверяю текущую сессию...")
    session_check = check_current_session(args.api_url)
    session_data = session_check.get("data", {})

    if session_data.get("is_valid", False) and not args.force:
        print("✅ Сессия уже валидна!")

        # Тестируем получение автомобилей
        print("\n🚗 Тестирую получение списка автомобилей...")
        car_test = test_car_list(args.api_url)
        if car_test["success"] and car_test["cars_count"] > 0:
            print(f"✅ Успешно получено {car_test['cars_count']} автомобилей")
            print("🎉 Все работает корректно! Восстановление не требуется.")
            return 0
        else:
            print(f"⚠️ Проблема с получением автомобилей: {car_test['message']}")
            print("🔄 Продолжаю восстановление сессии...")
    else:
        issues = session_data.get("issues", ["Неизвестная проблема"])
        print("❌ Проблемы с сессией:")
        for issue in issues:
            print(f"   - {issue}")

    # Шаг 3: Выполняем автоматический вход
    print("\n3️⃣ Выполняю автоматический вход в Glovis...")
    if run_auto_login(args.api_url):
        print("✅ Автоматический вход выполнен")
    else:
        print("❌ Не удалось выполнить автоматический вход")
        print("\n🔧 Попробуйте выполнить вручную:")
        print(f"   python glovis_auto_login.py --api-url {args.api_url} --update-api")
        return 1

    # Шаг 4: Проверяем восстановленную сессию
    print("\n4️⃣ Проверяю восстановленную сессию...")
    time.sleep(2)  # Небольшая пауза для обновления

    session_check = check_current_session(args.api_url)
    session_data = session_check.get("data", {})

    if session_data.get("is_valid", False):
        print("✅ Сессия успешно восстановлена!")

        # Финальный тест
        print("\n🚗 Финальный тест получения автомобилей...")
        car_test = test_car_list(args.api_url)
        if car_test["success"] and car_test["cars_count"] > 0:
            print(f"✅ Успешно получено {car_test['cars_count']} автомобилей")
            print("\n🎉 Сессия полностью восстановлена! API готово к работе.")

            # Показываем информацию о сессии
            cookies_info = session_data.get("cookies_info", {})
            if "JSESSIONID" in cookies_info:
                jsession = cookies_info["JSESSIONID"]["value"][:20] + "..."
                print(f"🍪 JSESSIONID: {jsession}")

            return 0
        else:
            print(
                f"⚠️ Сессия восстановлена, но есть проблемы с API: {car_test['message']}"
            )
            return 1
    else:
        issues = session_data.get("issues", ["Неизвестная проблема"])
        print("❌ Не удалось восстановить сессию:")
        for issue in issues:
            print(f"   - {issue}")

        print("\n🔧 Дополнительные шаги для решения:")
        print("   1. Проверьте интернет-соединение")
        print("   2. Убедитесь что сайт Glovis доступен")
        print("   3. Проверьте правильность учетных данных в auctions-auth.txt")
        print("   4. Попробуйте выполнить вход вручную на сайте Glovis")

        return 1


if __name__ == "__main__":
    exit(main())
