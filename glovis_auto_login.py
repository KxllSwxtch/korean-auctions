#!/usr/bin/env python3
"""
Автоматический вход в Glovis аукцион
Скрипт автоматически входит в систему Glovis и получает новые валидные cookies
"""

import requests
import json
import time
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from typing import Dict, Any, Optional
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class GlovisAutoLogin:
    """Класс для автоматического входа в Glovis"""

    def __init__(self):
        self.base_url = "https://auction.autobell.co.kr"
        self.session = None
        self.login_data = {"username": "7552", "password": "for7721@"}

    def _create_session(self) -> requests.Session:
        """Создает новую сессию"""
        session = requests.Session()

        # Настройка headers
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
        )

        session.verify = False
        return session

    def login(self) -> Dict[str, Any]:
        """
        Выполняет вход в Glovis

        Returns:
            Dict с результатом входа и cookies
        """
        try:
            print("🚀 Начинаю автоматический вход в Glovis...")

            # Создаем новую сессию
            self.session = self._create_session()

            # Шаг 1: Получаем главную страницу
            print("📄 Получаю главную страницу...")
            main_page = self.session.get(f"{self.base_url}/", timeout=30)
            if main_page.status_code != 200:
                return {
                    "success": False,
                    "message": f"Ошибка загрузки главной страницы: {main_page.status_code}",
                }

            # Шаг 2: Получаем страницу логина
            print("🔐 Получаю страницу логина...")
            login_page_url = f"{self.base_url}/login/loginMember.do"
            login_page = self.session.get(login_page_url, timeout=30)
            if login_page.status_code != 200:
                return {
                    "success": False,
                    "message": f"Ошибка загрузки страницы логина: {login_page.status_code}",
                }

            # Парсим страницу логина для поиска дополнительных параметров
            soup = BeautifulSoup(login_page.text, "html.parser")

            # Шаг 3: Выполняем логин
            print(f"🔑 Выполняю вход для пользователя {self.login_data['username']}...")

            login_data = {
                "username": self.login_data["username"],
                "password": self.login_data["password"],
                "loginType": "M",  # Member login
                "returnUrl": "",
            }

            # Находим форму логина и дополнительные поля
            form = soup.find("form", {"name": "loginForm"}) or soup.find(
                "form", id="loginForm"
            )
            if form:
                for input_field in form.find_all("input", type="hidden"):
                    name = input_field.get("name")
                    value = input_field.get("value", "")
                    if name and name not in login_data:
                        login_data[name] = value
                        print(f"   📋 Найден скрытый параметр: {name} = {value}")

            # Устанавливаем правильные headers для логина
            self.session.headers.update(
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                    "Referer": login_page_url,
                }
            )

            login_response = self.session.post(
                f"{self.base_url}/login/loginMemberProcess.do",
                data=login_data,
                timeout=30,
                allow_redirects=True,
            )

            print(f"📊 Ответ логина: {login_response.status_code}")
            print(f"📍 Финальный URL: {login_response.url}")

            # Шаг 4: Проверяем успешность входа
            if (
                "login" in login_response.url.lower()
                or login_response.status_code == 401
            ):
                return {
                    "success": False,
                    "message": "Неверные учетные данные или ошибка входа",
                }

            # Шаг 5: Получаем cookies
            cookies = {}
            for cookie in self.session.cookies:
                cookies[cookie.name] = cookie.value

            print(f"🍪 Получено {len(cookies)} cookies:")
            for name, value in cookies.items():
                value_preview = value[:20] + "..." if len(value) > 20 else value
                print(f"   - {name}: {value_preview}")

            # Шаг 6: Проверяем доступ к аукциону
            print("🏁 Проверяю доступ к аукциону...")
            auction_url = f"{self.base_url}/auction/exhibitList.do"
            auction_params = {"atn": "946", "acc": "20", "flag": "Y"}

            auction_response = self.session.get(
                auction_url, params=auction_params, timeout=30
            )

            if (
                auction_response.status_code == 200
                and "login" not in auction_response.text.lower()
            ):
                print("✅ Успешный вход! Доступ к аукциону подтвержден")

                return {
                    "success": True,
                    "message": "Успешный вход в Glovis",
                    "cookies": cookies,
                    "session_data": {
                        "login_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "username": self.login_data["username"],
                        "auction_access": True,
                        "jsessionid": cookies.get("JSESSIONID"),
                    },
                }
            else:
                return {
                    "success": False,
                    "message": "Вход выполнен, но нет доступа к аукциону",
                }

        except Exception as e:
            print(f"❌ Ошибка при входе: {str(e)}")
            return {"success": False, "message": f"Ошибка входа: {str(e)}"}
        finally:
            if self.session:
                self.session.close()

    def update_cookies_in_api(
        self, cookies: Dict[str, str], api_url: str = "http://localhost:8000"
    ) -> bool:
        """Обновляет cookies в API"""
        try:
            print(f"🔄 Обновляю cookies в API ({api_url})...")

            response = requests.post(
                f"{api_url}/api/v1/glovis/update-cookies", json=cookies, timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Cookies успешно обновлены в API: {result['message']}")
                return True
            else:
                print(f"❌ Ошибка обновления cookies в API: {response.status_code}")
                print(f"Ответ: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Ошибка при обновлении cookies в API: {e}")
            return False


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Автоматический вход в Glovis")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="URL API сервера (по умолчанию: http://localhost:8000)",
    )
    parser.add_argument(
        "--save-cookies", action="store_true", help="Сохранить cookies в файл"
    )
    parser.add_argument(
        "--update-api", action="store_true", help="Обновить cookies в API автоматически"
    )

    args = parser.parse_args()

    print("🔐 Автоматический вход в Glovis")
    print(f"🌐 API URL: {args.api_url}")
    print()

    # Выполняем вход
    auto_login = GlovisAutoLogin()
    result = auto_login.login()

    if result["success"]:
        print(f"\n✅ {result['message']}")

        cookies = result["cookies"]

        # Сохраняем cookies в файл если запрошено
        if args.save_cookies:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"glovis_cookies_{timestamp}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    {"cookies": cookies, "session_data": result["session_data"]},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            print(f"💾 Cookies сохранены в файл: {filename}")

        # Обновляем cookies в API если запрошено
        if args.update_api:
            auto_login.update_cookies_in_api(cookies, args.api_url)

        print(f"\n🎯 Для обновления cookies в API выполните:")
        print(f"   python update_glovis_cookies.py --api-url {args.api_url}")

    else:
        print(f"\n❌ {result['message']}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
