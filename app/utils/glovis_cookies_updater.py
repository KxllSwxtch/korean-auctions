"""
Утилита для обновления cookies Glovis из curl запросов
"""

import re
from typing import Dict, Optional
from datetime import datetime


class GlovisCookiesUpdater:
    """Утилита для извлечения и обновления cookies из curl запросов"""

    @staticmethod
    def extract_cookies_from_curl_file(file_path: str) -> Optional[Dict[str, str]]:
        """
        Извлекает cookies из Python файла с curl запросом

        Args:
            file_path: Путь к файлу с curl запросом

        Returns:
            Dict с cookies или None если не удалось извлечь
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Ищем cookies в формате словаря Python
            cookies_match = re.search(r"cookies\s*=\s*{([^}]+)}", content, re.DOTALL)
            if not cookies_match:
                return None

            cookies_content = cookies_match.group(1)
            cookies = {}

            # Извлекаем каждый cookie
            cookie_matches = re.findall(r'"([^"]+)":\s*"([^"]+)"', cookies_content)
            for name, value in cookie_matches:
                cookies[name] = value

            return cookies

        except Exception as e:
            print(f"Ошибка при извлечении cookies: {e}")
            return None

    @staticmethod
    def extract_data_from_curl_file(file_path: str) -> Optional[Dict[str, str]]:
        """
        Извлекает data параметры из Python файла с curl запросом

        Args:
            file_path: Путь к файлу с curl запросом

        Returns:
            Dict с data параметрами или None если не удалось извлечь
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Ищем data в формате словаря Python
            data_match = re.search(r"data\s*=\s*{([^}]+)}", content, re.DOTALL)
            if not data_match:
                return None

            data_content = data_match.group(1)
            data = {}

            # Извлекаем каждый параметр data
            data_matches = re.findall(r'"([^"]+)":\s*"([^"]+)"', data_content)
            for name, value in data_matches:
                data[name] = value

            return data

        except Exception as e:
            print(f"Ошибка при извлечении data: {e}")
            return None

    @staticmethod
    def extract_headers_from_curl_file(file_path: str) -> Optional[Dict[str, str]]:
        """
        Извлекает headers из Python файла с curl запросом

        Args:
            file_path: Путь к файлу с curl запросом

        Returns:
            Dict с headers или None если не удалось извлечь
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Ищем headers в формате словаря Python
            headers_match = re.search(r"headers\s*=\s*{([^}]+)}", content, re.DOTALL)
            if not headers_match:
                return None

            headers_content = headers_match.group(1)
            headers = {}

            # Извлекаем каждый header
            header_matches = re.findall(r'"([^"]+)":\s*"([^"]+)"', headers_content)
            for name, value in header_matches:
                headers[name] = value

            return headers

        except Exception as e:
            print(f"Ошибка при извлечении headers: {e}")
            return None

    @staticmethod
    def format_cookies_for_python(cookies: Dict[str, str]) -> str:
        """
        Форматирует cookies для вставки в Python код

        Args:
            cookies: Dict с cookies

        Returns:
            Отформатированная строка с cookies
        """
        lines = []
        lines.append(
            f'        """Возвращает свежие cookies для Glovis (обновлено {datetime.now().strftime("%Y-%m-%d")})"""'
        )
        lines.append("        # Обновленные cookies из рабочего curl запроса")
        lines.append("        return {")

        for name, value in cookies.items():
            lines.append(f'            "{name}": "{value}",')

        lines.append("        }")

        return "\n".join(lines)

    @staticmethod
    def get_jsessionid_from_cookies(cookies: Dict[str, str]) -> Optional[str]:
        """
        Извлекает JSESSIONID из cookies

        Args:
            cookies: Dict с cookies

        Returns:
            JSESSIONID или None если не найден
        """
        return cookies.get("JSESSIONID")

    @staticmethod
    def is_jsessionid_valid(jsessionid: str) -> bool:
        """
        Проверяет формат JSESSIONID

        Args:
            jsessionid: JSESSIONID для проверки

        Returns:
            True если формат валидный
        """
        if not jsessionid:
            return False

        # JSESSIONID обычно имеет формат: base64_string.server_info
        parts = jsessionid.split(".")
        if len(parts) != 2:
            return False

        # Первая часть должна быть base64-подобной
        if len(parts[0]) < 32:
            return False

        return True

    @classmethod
    def update_cookies_from_curl_file(cls, file_path: str) -> Dict[str, any]:
        """
        Полное обновление cookies из curl файла

        Args:
            file_path: Путь к файлу с curl запросом

        Returns:
            Dict с результатом обновления
        """
        result = {
            "success": False,
            "cookies": None,
            "jsessionid": None,
            "data": None,
            "headers": None,
            "message": "",
        }

        try:
            # Извлекаем cookies
            cookies = cls.extract_cookies_from_curl_file(file_path)
            if not cookies:
                result["message"] = "Не удалось извлечь cookies из файла"
                return result

            # Извлекаем JSESSIONID
            jsessionid = cls.get_jsessionid_from_cookies(cookies)
            if not jsessionid:
                result["message"] = "JSESSIONID не найден в cookies"
                return result

            if not cls.is_jsessionid_valid(jsessionid):
                result["message"] = "JSESSIONID имеет неверный формат"
                return result

            # Извлекаем data и headers
            data = cls.extract_data_from_curl_file(file_path)
            headers = cls.extract_headers_from_curl_file(file_path)

            result.update(
                {
                    "success": True,
                    "cookies": cookies,
                    "jsessionid": jsessionid,
                    "data": data,
                    "headers": headers,
                    "message": f"Успешно извлечены данные из {file_path}",
                }
            )

            return result

        except Exception as e:
            result["message"] = f"Ошибка при обновлении cookies: {e}"
            return result
