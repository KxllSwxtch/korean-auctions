#!/usr/bin/env python3
"""
Быстрое восстановление Glovis
Скрипт для быстрого обновления cookies из JSON файла или прямого ввода
"""

import requests
import json
import sys
from typing import Dict, Any


def update_cookies_from_json(
    json_file: str, api_url: str = "http://localhost:8000"
) -> bool:
    """Обновляет cookies из JSON файла"""
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        print(f"📁 Загружено {len(cookies)} cookies из {json_file}")

        response = requests.post(
            f"{api_url}/api/v1/glovis/update-cookies", json=cookies, timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ {result['message']}")
            return True
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def update_cookies_from_input(api_url: str = "http://localhost:8000") -> bool:
    """Обновляет cookies из ввода пользователя"""
    print("🍪 Введите cookies в JSON формате:")
    print('Пример: {"JSESSIONID": "значение", "SCOUTER": "значение"}')
    print("Введите JSON и нажмите Enter (для завершения введите пустую строку):")

    lines = []
    while True:
        try:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        except KeyboardInterrupt:
            print("\n❌ Отменено пользователем")
            return False

    json_text = "\n".join(lines)

    try:
        cookies = json.loads(json_text)

        print(f"📋 Обрабатываю {len(cookies)} cookies...")

        response = requests.post(
            f"{api_url}/api/v1/glovis/update-cookies", json=cookies, timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ {result['message']}")
            return True
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            return False

    except json.JSONDecodeError as e:
        print(f"❌ Ошибка JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_api(api_url: str = "http://localhost:8000") -> None:
    """Тестирует API после обновления"""
    print("\n🧪 Тестирую API...")

    try:
        # Проверяем сессию
        session_response = requests.get(
            f"{api_url}/api/v1/glovis/check-session", timeout=30
        )
        if session_response.status_code == 200:
            session_data = session_response.json().get("data", {})
            if session_data.get("is_valid", False):
                print("✅ Сессия валидна")
            else:
                print("⚠️ Проблемы с сессией:")
                for issue in session_data.get("issues", []):
                    print(f"   - {issue}")

        # Тестируем получение автомобилей
        cars_response = requests.get(f"{api_url}/api/v1/glovis/cars?page=1", timeout=30)
        if cars_response.status_code == 200:
            cars_data = cars_response.json()
            if cars_data.get("success", False):
                cars_count = len(cars_data.get("cars", []))
                print(f"✅ Получено {cars_count} автомобилей")
                print("🎉 API работает корректно!")
            else:
                print(
                    f"❌ Ошибка API: {cars_data.get('message', 'Неизвестная ошибка')}"
                )
        else:
            print(f"❌ HTTP ошибка: {cars_response.status_code}")

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Быстрое восстановление Glovis")
    parser.add_argument("--json-file", help="JSON файл с cookies")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="URL API сервера"
    )
    parser.add_argument(
        "--test", action="store_true", help="Протестировать API после обновления"
    )

    args = parser.parse_args()

    print("🚀 Быстрое восстановление Glovis")
    print(f"🌐 API URL: {args.api_url}")
    print()

    success = False

    if args.json_file:
        # Обновление из JSON файла
        success = update_cookies_from_json(args.json_file, args.api_url)
    else:
        # Обновление из ввода пользователя
        success = update_cookies_from_input(args.api_url)

    if success and args.test:
        test_api(args.api_url)
    elif success:
        print("\n🎯 Для тестирования выполните:")
        print(f"   python quick_fix_glovis.py --test --api-url {args.api_url}")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
