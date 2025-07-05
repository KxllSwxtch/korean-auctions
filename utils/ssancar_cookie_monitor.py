#!/usr/bin/env python3
"""
Утилита для мониторинга и обновления cookies SSANCAR
Помогает отслеживать изменения в cookies и автоматически обновлять параметры
"""

import requests
import json
import os
from datetime import datetime
from typing import Dict, Optional


class SSANCARCookieMonitor:
    """Мониторинг cookies и параметров SSANCAR"""

    def __init__(self):
        self.base_url = "https://www.ssancar.com"
        self.list_url = f"{self.base_url}/bbs/board.php?bo_table=list"
        self.api_url = f"{self.base_url}/ajax/ajax_car_list.php"
        self.config_file = "ssancar_cookies.json"

    def extract_cookies_from_main_page(self) -> Optional[Dict[str, str]]:
        """Извлекает актуальные cookies с главной страницы SSANCAR"""
        try:
            print("🔍 Анализируем главную страницу SSANCAR...")

            # Первый запрос для получения cookies
            response = requests.get(self.list_url, timeout=30)

            if response.status_code == 200:
                cookies = {}
                for cookie in response.cookies:
                    cookies[cookie.name] = cookie.value

                print(f"✅ Получены cookies: {list(cookies.keys())}")
                return cookies
            else:
                print(f"❌ Ошибка получения главной страницы: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Ошибка при извлечении cookies: {e}")
            return None

    def test_cookies(self, cookies: Dict[str, str]) -> bool:
        """Тестирует работоспособность cookies"""
        try:
            print("🧪 Тестируем cookies...")

            headers = {
                "Accept": "*/*",
                "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.base_url,
                "Referer": self.list_url,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }

            # Динамическое определение weekNo (как в основном сервисе)
            from datetime import datetime

            now = datetime.now()
            weekday = now.weekday()

            if weekday in [0, 1]:  # Понедельник или Вторник
                week_no = "1"
            elif weekday in [3, 4]:  # Четверг или Пятница
                week_no = "2"
            else:  # Остальные дни
                week_no = "1"

            data = {
                "weekNo": week_no,
                "maker": "",
                "model": "",
                "fuel": "",
                "color": "",
                "yearFrom": "2000",
                "yearTo": "2025",
                "priceFrom": "0",
                "priceTo": "200000",
                "list": "15",
                "pages": "0",
                "no": "",
            }

            response = requests.post(
                self.api_url, cookies=cookies, headers=headers, data=data, timeout=30
            )

            if response.status_code == 200 and len(response.text) > 1000:
                print("✅ Cookies работают корректно!")
                return True
            else:
                print(
                    f"❌ Cookies не работают. Status: {response.status_code}, Length: {len(response.text)}"
                )
                return False

        except Exception as e:
            print(f"❌ Ошибка при тестировании cookies: {e}")
            return False

    def save_cookies_config(self, cookies: Dict[str, str]):
        """Сохраняет конфигурацию cookies"""
        try:
            config = {
                "timestamp": datetime.now().isoformat(),
                "cookies": cookies,
                "status": "active",
            }

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            print(f"💾 Конфигурация сохранена в {self.config_file}")

        except Exception as e:
            print(f"❌ Ошибка при сохранении конфигурации: {e}")

    def load_cookies_config(self) -> Optional[Dict]:
        """Загружает сохраненную конфигурацию cookies"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return None
        except Exception as e:
            print(f"❌ Ошибка при загрузке конфигурации: {e}")
            return None

    def generate_service_update(self, cookies: Dict[str, str]):
        """Генерирует код для обновления сервиса"""
        print("\n" + "=" * 60)
        print("📝 КОД ДЛЯ ОБНОВЛЕНИЯ GLOVIS SERVICE:")
        print("=" * 60)

        print("# Обновите следующие строки в app/services/glovis_service.py:")
        print()
        print("self._default_cookies = {")
        for key, value in cookies.items():
            print(f'    "{key}": "{value}",')
        print("}")
        print()
        print("=" * 60)

    def monitor_and_update(self):
        """Основной метод мониторинга и обновления"""
        print("🔧 МОНИТОРИНГ COOKIES SSANCAR")
        print("=" * 60)

        # 1. Загружаем старую конфигурацию
        old_config = self.load_cookies_config()
        if old_config:
            print(f"📁 Загружена старая конфигурация от {old_config['timestamp']}")
            old_cookies = old_config.get("cookies", {})
        else:
            print("📁 Старая конфигурация не найдена")
            old_cookies = {}

        # 2. Получаем новые cookies
        new_cookies = self.extract_cookies_from_main_page()
        if not new_cookies:
            print("❌ Не удалось получить новые cookies")
            return False

        # 3. Сравниваем cookies
        if old_cookies and old_cookies == new_cookies:
            print("✅ Cookies не изменились, проверяем работоспособность...")
            if self.test_cookies(new_cookies):
                print("✅ Текущие cookies работают корректно")
                return True
            else:
                print("⚠️ Текущие cookies не работают, требуется обновление")
        else:
            print("🔄 Обнаружены изменения в cookies")

            # Показываем различия
            for key in set(list(old_cookies.keys()) + list(new_cookies.keys())):
                old_val = old_cookies.get(key, "НЕТ")
                new_val = new_cookies.get(key, "НЕТ")
                if old_val != new_val:
                    print(f"  {key}: {old_val} → {new_val}")

        # 4. Тестируем новые cookies
        if self.test_cookies(new_cookies):
            print("✅ Новые cookies работают!")

            # 5. Сохраняем новую конфигурацию
            self.save_cookies_config(new_cookies)

            # 6. Генерируем код для обновления
            self.generate_service_update(new_cookies)

            return True
        else:
            print("❌ Новые cookies не работают")
            return False


def main():
    """Главная функция"""
    monitor = SSANCARCookieMonitor()
    success = monitor.monitor_and_update()

    print("\n" + "=" * 60)
    if success:
        print("🎉 МОНИТОРИНГ ЗАВЕРШЕН УСПЕШНО")
    else:
        print("💥 ТРЕБУЕТСЯ РУЧНАЯ ПРОВЕРКА")
    print("=" * 60)


if __name__ == "__main__":
    main()
