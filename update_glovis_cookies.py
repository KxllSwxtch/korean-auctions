#!/usr/bin/env python3
"""
Утилита для быстрого обновления cookies Glovis
Автоматически извлекает cookies из файла glovis-curl-request.py и обновляет их в API
"""

import requests
import json
import re
from pathlib import Path
from typing import Dict, Any


def extract_cookies_from_curl_file(
    file_path: str = "glovis-curl-request.py",
) -> Dict[str, str]:
    """Извлекает cookies из файла с CURL запросом"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Ищем блок cookies в файле
        cookies_match = re.search(r"cookies\s*=\s*{([^}]+)}", content, re.DOTALL)
        if not cookies_match:
            raise ValueError("Не найден блок cookies в файле")

        cookies_block = cookies_match.group(1)

        # Парсим cookies
        cookies = {}
        for line in cookies_block.split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                # Удаляем кавычки и запятые
                line = line.rstrip(",")
                key_value = line.split(":", 1)
                if len(key_value) == 2:
                    key = key_value[0].strip().strip('"')
                    value = key_value[1].strip().strip('"')
                    cookies[key] = value

        return cookies

    except Exception as e:
        print(f"❌ Ошибка при извлечении cookies из файла: {e}")
        return {}


def update_cookies_via_api(
    cookies: Dict[str, str], api_url: str = "http://localhost:8000"
) -> bool:
    """Обновляет cookies через API"""
    try:
        response = requests.post(
            f"{api_url}/api/v1/glovis/update-cookies", json=cookies, timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Cookies успешно обновлены: {result['message']}")

            # Показываем статус сессии
            session_status = result.get("data", {}).get("new_session_status", {})
            if session_status.get("is_valid", False):
                print("✅ Новая сессия валидна")
            else:
                print("⚠️ Проблемы с новой сессией:")
                for issue in session_status.get("issues", []):
                    print(f"   - {issue}")

            return True
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            print(f"Ответ: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Ошибка при обновлении cookies: {e}")
        return False


def check_session_status(api_url: str = "http://localhost:8000") -> None:
    """Проверяет текущий статус сессии"""
    try:
        response = requests.get(f"{api_url}/api/v1/glovis/check-session", timeout=30)

        if response.status_code == 200:
            result = response.json()
            session_data = result.get("data", {})

            print(f"\n{'='*60}")
            print("🔍 СТАТУС СЕССИИ GLOVIS")
            print(f"{'='*60}")

            if session_data.get("is_valid", False):
                print("✅ Сессия валидна")
                print(f"📊 Статус код: {session_data.get('status_code', 'N/A')}")
                print(
                    f"📁 Размер ответа: {session_data.get('response_size', 'N/A')} символов"
                )

                # Информация о JSESSIONID
                cookies_info = session_data.get("cookies_info", {})
                if "JSESSIONID" in cookies_info:
                    jsession = cookies_info["JSESSIONID"]
                    print(f"🍪 JSESSIONID: {jsession.get('value', 'N/A')}")
            else:
                print("❌ Проблемы с сессией:")
                for issue in session_data.get("issues", []):
                    print(f"   - {issue}")

            print(f"{'='*60}")

        else:
            print(f"❌ Ошибка при проверке сессии: {response.status_code}")

    except Exception as e:
        print(f"❌ Ошибка при проверке сессии: {e}")


def test_api_request(api_url: str = "http://localhost:8000") -> None:
    """Тестирует API запрос автомобилей"""
    try:
        print("\n🚗 Тестирую API запрос автомобилей...")
        response = requests.get(f"{api_url}/api/v1/glovis/cars", timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get("success", False):
                cars_count = len(result.get("data", {}).get("cars", []))
                total_count = result.get("data", {}).get("total_count", 0)
                print(
                    f"✅ API работает! Получено {cars_count} автомобилей из {total_count}"
                )
            else:
                print(
                    f"⚠️ API вернул ошибку: {result.get('message', 'Неизвестная ошибка')}"
                )
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")

    except Exception as e:
        print(f"❌ Ошибка при тестировании API: {e}")


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Обновление cookies для Glovis")
    parser.add_argument(
        "--file",
        default="glovis-curl-request.py",
        help="Путь к файлу с CURL запросом (по умолчанию: glovis-curl-request.py)",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="URL API сервера (по умолчанию: http://localhost:8000)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Только проверить статус сессии, не обновлять cookies",
    )
    parser.add_argument(
        "--test", action="store_true", help="Протестировать API после обновления"
    )

    args = parser.parse_args()

    print("🚀 Утилита обновления cookies Glovis")
    print(f"📁 Файл с cookies: {args.file}")
    print(f"🌐 API URL: {args.api_url}")
    print()

    # Проверяем текущий статус
    check_session_status(args.api_url)

    if args.check_only:
        print("\n✅ Проверка завершена (режим --check-only)")
        return

    # Извлекаем cookies из файла
    print(f"\n📖 Извлекаю cookies из файла {args.file}...")
    cookies = extract_cookies_from_curl_file(args.file)

    if not cookies:
        print("❌ Не удалось извлечь cookies из файла")
        return

    print(f"✅ Извлечено {len(cookies)} cookies:")
    for key in cookies.keys():
        value_preview = (
            cookies[key][:20] + "..." if len(cookies[key]) > 20 else cookies[key]
        )
        print(f"   - {key}: {value_preview}")

    # Обновляем cookies
    print(f"\n🔄 Обновляю cookies через API...")
    if update_cookies_via_api(cookies, args.api_url):
        print("✅ Cookies успешно обновлены")

        # Тестируем API если запрошено
        if args.test:
            test_api_request(args.api_url)
    else:
        print("❌ Не удалось обновить cookies")


if __name__ == "__main__":
    main()
