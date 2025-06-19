#!/usr/bin/env python3
"""
Автоматический конвертер cURL в cookies для Glovis
Упрощает процесс обновления cookies из скопированного cURL запроса
"""

import re
import json
import requests
import argparse
from typing import Dict, Optional, Tuple
from datetime import datetime
import urllib.parse


class GlovisCurlConverter:
    """Конвертер cURL команд в cookies для Glovis"""
    
    def __init__(self):
        self.api_url = "http://localhost:8000"
        
    def parse_curl_command(self, curl_command: str) -> Dict[str, str]:
        """
        Парсит cURL команду и извлекает cookies
        
        Args:
            curl_command: cURL команда, скопированная из DevTools
            
        Returns:
            Dict[str, str]: Извлеченные cookies
        """
        try:
            # Убираем переносы строк и лишние пробелы
            curl_command = re.sub(r'\\\s*\n\s*', ' ', curl_command)
            curl_command = re.sub(r'\s+', ' ', curl_command).strip()
            
            # Ищем cookie заголовок
            cookie_pattern = r"-H ['\"]cookie:\s*([^'\"]+)['\"]"
            cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
            
            if not cookie_match:
                # Альтернативный поиск без -H
                cookie_pattern = r"cookie:\s*['\"]([^'\"]+)['\"]"
                cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
            
            if not cookie_match:
                # Поиск через -b параметр (короткая форма cookies)
                cookie_pattern = r"-b ['\"]([^'\"]+)['\"]"
                cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
            
            if not cookie_match:
                # Поиск через --cookie параметр
                cookie_pattern = r"--cookie ['\"]([^'\"]+)['\"]"
                cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
            
            if not cookie_match:
                raise ValueError("Не найден cookie заголовок в cURL команде")
            
            cookie_string = cookie_match.group(1)
            
            # Парсим cookies
            cookies = {}
            for cookie_pair in cookie_string.split(';'):
                cookie_pair = cookie_pair.strip()
                if '=' in cookie_pair:
                    key, value = cookie_pair.split('=', 1)
                    cookies[key.strip()] = value.strip()
            
            # Проверяем наличие критичных cookies
            if 'JSESSIONID' not in cookies:
                raise ValueError("JSESSIONID не найден в cookies")
            
            print(f"✅ Извлечено {len(cookies)} cookies:")
            for key, value in cookies.items():
                value_preview = value[:20] + "..." if len(value) > 20 else value
                print(f"   - {key}: {value_preview}")
            
            return cookies
            
        except Exception as e:
            print(f"❌ Ошибка при парсинге cURL: {e}")
            return {}
    
    def validate_cookies(self, cookies: Dict[str, str]) -> bool:
        """
        Проверяет валидность cookies через тестовый запрос
        
        Args:
            cookies: Cookies для проверки
            
        Returns:
            bool: True если cookies валидны
        """
        try:
            print("🔍 Проверяю валидность cookies...")
            
            # Создаем тестовую сессию
            session = requests.Session()
            
            # Устанавливаем cookies
            for name, value in cookies.items():
                session.cookies.set(name, value)
            
            # Устанавливаем headers
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            })
            
            # Делаем тестовый запрос
            test_url = "https://auction.autobell.co.kr/auction/exhibitList.do"
            params = {"atn": "946", "acc": "20", "flag": "Y"}
            
            response = session.get(test_url, params=params, timeout=15, verify=False)
            
            # Проверяем результат
            if response.status_code == 200:
                # Проверяем, что нет редиректа на логин
                if "login" not in response.text.lower() or len(response.text) > 5000:
                    print("✅ Cookies валидны!")
                    return True
                else:
                    print("❌ Cookies истекли - перенаправление на логин")
                    return False
            else:
                print(f"❌ HTTP ошибка: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при валидации: {e}")
            return False
        finally:
            if 'session' in locals():
                session.close()
    
    def update_api_cookies(self, cookies: Dict[str, str]) -> bool:
        """
        Обновляет cookies в API
        
        Args:
            cookies: Новые cookies
            
        Returns:
            bool: True если обновление успешно
        """
        try:
            print(f"🔄 Обновляю cookies в API ({self.api_url})...")
            
            response = requests.post(
                f"{self.api_url}/api/v1/glovis/update-cookies",
                json=cookies,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Cookies обновлены в API: {result.get('message', 'Успешно')}")
                return True
            else:
                print(f"❌ Ошибка API: {response.status_code}")
                if response.text:
                    print(f"Ответ: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при обновлении API: {e}")
            return False
    
    def save_cookies_to_file(self, cookies: Dict[str, str], filename: Optional[str] = None) -> str:
        """
        Сохраняет cookies в файл
        
        Args:
            cookies: Cookies для сохранения
            filename: Имя файла (необязательно)
            
        Returns:
            str: Путь к сохраненному файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"glovis_cookies_{timestamp}.json"
        
        cookie_data = {
            "cookies": cookies,
            "timestamp": datetime.now().isoformat(),
            "source": "curl_converter",
            "jsessionid": cookies.get("JSESSIONID", "")
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(cookie_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Cookies сохранены в файл: {filename}")
        return filename
    
    def process_curl_from_clipboard(self) -> bool:
        """
        Обрабатывает cURL команду из буфера обмена
        
        Returns:
            bool: True если обработка успешна
        """
        try:
            import pyperclip
            curl_command = pyperclip.paste()
            
            if not curl_command or not curl_command.strip().startswith('curl'):
                print("❌ В буфере обмена нет cURL команды")
                return False
            
            print("📋 Получена cURL команда из буфера обмена")
            return self.process_curl_command(curl_command)
            
        except ImportError:
            print("❌ Модуль pyperclip не установлен")
            print("   Установите: pip install pyperclip")
            return False
        except Exception as e:
            print(f"❌ Ошибка при работе с буфером обмена: {e}")
            return False
    
    def process_curl_command(self, curl_command: str) -> bool:
        """
        Обрабатывает cURL команду полностью
        
        Args:
            curl_command: cURL команда
            
        Returns:
            bool: True если обработка успешна
        """
        print("🔄 Обрабатываю cURL команду...")
        
        # Парсим cookies
        cookies = self.parse_curl_command(curl_command)
        if not cookies:
            return False
        
        # Валидируем cookies
        if not self.validate_cookies(cookies):
            print("❌ Cookies не прошли валидацию")
            return False
        
        # Сохраняем в файл
        self.save_cookies_to_file(cookies)
        
        # Обновляем в API
        if self.update_api_cookies(cookies):
            print("🎉 Cookies успешно обработаны и обновлены!")
            return True
        else:
            print("⚠️ Cookies обработаны, но не удалось обновить API")
            return False


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description="Конвертер cURL команд в cookies для Glovis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

1. Из буфера обмена (скопируйте cURL из DevTools):
   python glovis_curl_converter.py --from-clipboard

2. Из файла:
   python glovis_curl_converter.py --from-file curl_command.txt

3. Интерактивно:
   python glovis_curl_converter.py --interactive

4. Только парсинг без обновления API:
   python glovis_curl_converter.py --from-clipboard --no-api-update
        """
    )
    
    parser.add_argument(
        "--from-clipboard", 
        action="store_true",
        help="Получить cURL команду из буфера обмена"
    )
    parser.add_argument(
        "--from-file",
        help="Читать cURL команду из файла"
    )
    parser.add_argument(
        "--interactive",
        action="store_true", 
        help="Интерактивный ввод cURL команды"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="URL API сервера"
    )
    parser.add_argument(
        "--no-api-update",
        action="store_true",
        help="Не обновлять cookies в API"
    )
    parser.add_argument(
        "--save-only",
        action="store_true",
        help="Только сохранить в файл, не обновлять API"
    )
    
    args = parser.parse_args()
    
    print("🔄 Glovis cURL → Cookies Converter")
    print(f"🌐 API URL: {args.api_url}")
    print()
    
    converter = GlovisCurlConverter()
    converter.api_url = args.api_url
    
    curl_command = ""
    
    # Получаем cURL команду
    if args.from_clipboard:
        print("📋 Читаю из буфера обмена...")
        success = converter.process_curl_from_clipboard()
        return 0 if success else 1
        
    elif args.from_file:
        print(f"📄 Читаю из файла: {args.from_file}")
        try:
            with open(args.from_file, 'r', encoding='utf-8') as f:
                curl_command = f.read().strip()
        except Exception as e:
            print(f"❌ Ошибка чтения файла: {e}")
            return 1
            
    elif args.interactive:
        print("📝 Введите cURL команду (завершите пустой строкой):")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        curl_command = '\n'.join(lines)
        
    else:
        print("❌ Укажите способ получения cURL команды")
        print("   Используйте --help для справки")
        return 1
    
    if not curl_command:
        print("❌ Пустая cURL команда")
        return 1
    
    # Обрабатываем команду
    success = converter.process_curl_command(curl_command)
    
    if success:
        print("\n🎯 Cookies готовы к использованию!")
        print(f"   Проверьте работу: curl \"{args.api_url}/api/v1/glovis/cars?page=1\"")
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit(main())