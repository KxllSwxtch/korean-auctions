import requests
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from app.core.session_manager import SessionManager
from app.core.http_client import AsyncHttpClient
from app.models.heydealer import (
    LoginRequest,
    LoginResponse,
    HeyDealerFilters,
    HeyDealerCarList,
    HeyDealerDetailedCar,
)
from app.parsers.heydealer_parser import HeyDealerParser
from app.services.heydealer_auth_service import heydealer_auth

logger = logging.getLogger(__name__)


class HeyDealerService:
    """Сервис для работы с API HeyDealer"""

    def __init__(self):
        self.base_url = "https://api.heydealer.com"
        self.session_manager = SessionManager()
        self.service_name = "heydealer"
        self.http_client = AsyncHttpClient()
        self.parser = HeyDealerParser()
        self._session_id = None
        self._csrf_token = None
        self._cookies = {}

    def _get_headers(self) -> Dict[str, str]:
        """Получает заголовки для запросов"""
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "App-Os": "pc",
            "App-Type": "dealer",
            "App-Version": "1.9.0",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://dealer.heydealer.com",
            "Referer": "https://dealer.heydealer.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Используем CSRF токен из cookies, если есть
        csrf_token = self._cookies.get("csrftoken") or self._csrf_token
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        return headers

    def _get_initial_cookies(self) -> Dict[str, str]:
        """Получает начальные cookies для установки сессии"""
        return {
            "_ga": "GA1.2.225253972.1750804665",
            "_gid": "GA1.2.607092972.1750804665",
            "ga_dsi": "2f27c9738d9441acb3019f0388816973",
            "_gat": "1",
            "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750805823$j45$l0$h0",
        }

    async def authenticate(self, username: str, password: str) -> bool:
        """
        Аутентификация в системе HeyDealer

        Args:
            username: Имя пользователя
            password: Пароль

        Returns:
            True если аутентификация успешна, False иначе
        """
        try:
            # Проверяем сохраненную сессию
            saved_cookies = self.session_manager.load_session(self.service_name)
            if saved_cookies:
                # Попробуем загрузить полную сессию с метаданными из файла
                session_file = (
                    self.session_manager.cache_dir / f"{self.service_name}_session.json"
                )
                if session_file.exists():
                    import json

                    with open(session_file, "r", encoding="utf-8") as f:
                        session_data = json.load(f)

                    if self._is_session_valid(session_data):
                        self._restore_session(session_data)
                        logger.info("Использована сохраненная сессия HeyDealer")
                        return True

            # Устанавливаем начальные cookies
            self._cookies = self._get_initial_cookies()

            # Генерируем CSRF токен (можно использовать простой random)
            import secrets

            self._csrf_token = secrets.token_urlsafe(32)
            self._cookies["csrftoken"] = self._csrf_token

            # Подготавливаем данные для логина
            login_data = LoginRequest(
                username=username, password=password, device_type="pc"
            )

            # Выполняем запрос авторизации
            response = await self.http_client.post(
                url=f"{self.base_url}/v2/dealers/web/login/",
                json=login_data.model_dump(),
                headers=self._get_headers(),
                cookies=self._cookies,
            )

            if response.status_code == 200:
                data = response.json()
                login_response = LoginResponse(**data)

                # Обновляем cookies из ответа
                if response.cookies:
                    for cookie_key, cookie_value in response.cookies.items():
                        self._cookies[cookie_key] = cookie_value

                    # Получаем sessionid если есть
                    if "sessionid" in self._cookies:
                        self._session_id = self._cookies["sessionid"]

                # Сохраняем сессию
                metadata = {
                    "user_hash_id": login_response.user.hash_id,
                    "session_id": self._session_id,
                    "csrf_token": self._csrf_token,
                    "authenticated_at": datetime.now().isoformat(),
                }
                self.session_manager.save_session(
                    self.service_name, self._cookies, metadata
                )

                logger.info(
                    f"Успешная аутентификация HeyDealer для пользователя {login_response.user.hash_id}"
                )
                return True
            else:
                logger.error(
                    f"Ошибка аутентификации HeyDealer: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Исключение при аутентификации HeyDealer: {e}")
            return False

    def _is_session_valid(self, session_data: Dict[str, Any]) -> bool:
        """Проверяет валидность сохраненной сессии"""
        try:
            metadata = session_data.get("metadata", {})
            if not metadata.get("session_id") or not metadata.get("csrf_token"):
                return False

            auth_time = datetime.fromisoformat(metadata.get("authenticated_at", ""))
            # Сессия валидна 24 часа
            return datetime.now() - auth_time < timedelta(hours=24)
        except:
            return False

    def _restore_session(self, session_data: Dict[str, Any]) -> None:
        """Восстанавливает сессию из сохраненных данных"""
        metadata = session_data.get("metadata", {})
        self._session_id = metadata.get("session_id")
        self._csrf_token = metadata.get("csrf_token")
        self._cookies = session_data.get("cookies", {})

    async def ensure_authenticated(self) -> bool:
        """Обеспечивает аутентификацию (использует автоматический сервис)"""
        try:
            headers, cookies = heydealer_auth.get_headers_and_cookies()
            if headers and cookies:
                self._cookies = cookies
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при обеспечении аутентификации: {e}")
            return False

    async def get_user_info(self, user_hash_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о пользователе

        Args:
            user_hash_id: Hash ID пользователя

        Returns:
            Информация о пользователе или None при ошибке
        """
        try:
            response = await self.http_client.get(
                url=f"{self.base_url}/v2/dealers/web/users/{user_hash_id}/",
                headers=self._get_headers(),
                cookies=self._cookies,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Ошибка получения информации о пользователе: {response.status_code}"
                )
                return None

        except Exception as e:
            logger.error(f"Исключение при получении информации о пользователе: {e}")
            return None

    async def get_cars(self, filters: HeyDealerFilters) -> Optional[HeyDealerCarList]:
        """
        Получает список автомобилей с фильтрами

        Args:
            filters: Параметры фильтрации

        Returns:
            Список автомобилей или None при ошибке
        """
        try:
            # Подготавливаем параметры запроса
            params = {
                "page": str(filters.page),
                "type": filters.type,
                "is_subscribed": "true" if filters.is_subscribed else "false",
                "is_retried": "true" if filters.is_retried else "false",
                "is_previously_bid": "true" if filters.is_previously_bid else "false",
                "order": filters.order,
            }

            response = await self.http_client.get(
                url=f"{self.base_url}/v2/dealers/web/cars/",
                params=params,
                headers=self._get_headers(),
                cookies=self._cookies,
            )

            if response.status_code == 200:
                raw_data = response.json()

                # Парсим данные через HeyDealerParser
                parsed_data = self.parser.parse_car_list(raw_data)
                return parsed_data
            else:
                logger.error(
                    f"Ошибка получения списка автомобилей: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Исключение при получении списка автомобилей: {e}")
            return None

    async def fetch_cars_with_auth(
        self, username: str, password: str, filters: Optional[HeyDealerFilters] = None
    ) -> Optional[HeyDealerCarList]:
        """
        Получает автомобили с автоматической аутентификацией

        Args:
            username: Имя пользователя
            password: Пароль
            filters: Параметры фильтрации

        Returns:
            Список автомобилей или None при ошибке
        """
        try:
            # Аутентификация
            if not await self.authenticate(username, password):
                logger.error("Не удалось аутентифицироваться в HeyDealer")
                return None

            # Используем стандартные фильтры если не переданы
            if filters is None:
                filters = HeyDealerFilters()

            # Получаем автомобили
            return await self.get_cars(filters)

        except Exception as e:
            logger.error(f"Исключение при получении автомобилей с аутентификацией: {e}")
            return None

    async def get_car_detail(self, car_hash_id: str) -> Optional[HeyDealerDetailedCar]:
        """
        Получает детальную информацию об автомобиле

        Args:
            car_hash_id: Hash ID автомобиля

        Returns:
            Детальная информация об автомобиле или None при ошибке
        """
        try:
            response = await self.http_client.get(
                url=f"{self.base_url}/v2/dealers/web/cars/{car_hash_id}/",
                headers=self._get_headers(),
                cookies=self._cookies,
            )

            if response.status_code == 200:
                data = response.json()
                detailed_car = self.parser.parse_detailed_car(data)

                if detailed_car:
                    logger.info(
                        f"Получена детальная информация об автомобиле {car_hash_id}"
                    )
                    return detailed_car
                else:
                    logger.error(
                        f"Ошибка парсинга детальной информации автомобиля {car_hash_id}"
                    )
                    return None
            else:
                logger.error(
                    f"Ошибка получения детальной информации об автомобиле {car_hash_id}: "
                    f"{response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Исключение при получении детальной информации об автомобиле {car_hash_id}: {e}"
            )
            return None

    async def fetch_car_detail_with_auth(
        self, username: str, password: str, car_hash_id: str
    ) -> Optional[HeyDealerDetailedCar]:
        """
        Получает детальную информацию об автомобиле с аутентификацией

        Args:
            username: Имя пользователя
            password: Пароль
            car_hash_id: Hash ID автомобиля

        Returns:
            Детальная информация об автомобиле или None при ошибке
        """
        try:
            # Аутентификация
            if not await self.authenticate(username, password):
                logger.error(
                    "Ошибка аутентификации при получении детальной информации об автомобиле"
                )
                return None

            # Получение детальной информации
            return await self.get_car_detail(car_hash_id)

        except Exception as e:
            logger.error(
                f"Исключение при получении детальной информации об автомобиле с аутентификацией: {e}"
            )
            return None

    # === МЕТОДЫ ДЛЯ ФИЛЬТРОВ ===

    async def get_brands(self) -> List[Dict[str, Any]]:
        """Получение списка марок автомобилей"""
        try:
            await self.ensure_authenticated()

            params = {
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false",
                "is_previously_bid": "false",
            }

            response = await self.http_client.get(
                f"{self.base_url}/v2/dealers/web/car_meta/brands/", params=params
            )

            if response.status_code == 200:
                brands_data = response.json()
                logger.info(f"Получено {len(brands_data)} марок")
                return brands_data
            else:
                logger.error(f"Ошибка получения марок: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Ошибка при получении марок: {str(e)}")
            return []

    async def get_brand_models(self, brand_hash_id: str) -> Dict[str, Any]:
        """Получение списка моделей для марки"""
        try:
            await self.ensure_authenticated()

            params = {
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false",
                "is_previously_bid": "false",
            }

            response = await self.http_client.get(
                f"{self.base_url}/v2/dealers/web/car_meta/brands/{brand_hash_id}/",
                params=params,
            )

            if response.status_code == 200:
                brand_data = response.json()
                logger.info(f"Получены модели для марки {brand_hash_id}")
                return brand_data
            else:
                logger.error(f"Ошибка получения моделей: {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Ошибка при получении моделей: {str(e)}")
            return {}

    async def get_model_generations(self, model_group_hash_id: str) -> Dict[str, Any]:
        """Получение списка поколений для модели"""
        try:
            await self.ensure_authenticated()

            params = {
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false",
                "is_previously_bid": "false",
                "model_group": model_group_hash_id,
            }

            response = await self.http_client.get(
                f"{self.base_url}/v2/dealers/web/car_meta/model_groups/{model_group_hash_id}/",
                params=params,
            )

            if response.status_code == 200:
                model_data = response.json()
                logger.info(f"Получены поколения для модели {model_group_hash_id}")
                return model_data
            else:
                logger.error(f"Ошибка получения поколений: {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Ошибка при получении поколений: {str(e)}")
            return {}

    async def get_model_configurations(self, model_hash_id: str) -> Dict[str, Any]:
        """Получение списка конфигураций для поколения"""
        try:
            await self.ensure_authenticated()

            params = {
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false",
                "is_previously_bid": "false",
                "model": model_hash_id,
            }

            response = await self.http_client.get(
                f"{self.base_url}/v2/dealers/web/car_meta/models/{model_hash_id}/",
                params=params,
            )

            if response.status_code == 200:
                config_data = response.json()
                logger.info(f"Получены конфигурации для поколения {model_hash_id}")
                return config_data
            else:
                logger.error(f"Ошибка получения конфигураций: {response.status_code}")
                return {}

        except Exception as e:
            logger.error(f"Ошибка при получении конфигураций: {str(e)}")
            return {}

    async def get_filtered_cars(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение отфильтрованного списка автомобилей"""
        try:
            await self.ensure_authenticated()

            # Базовые параметры
            params = {
                "page": filters.get("page", 1),
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false",
                "is_previously_bid": "false",
                "order": filters.get("order", "default"),
            }

            # Добавляем фильтры если они указаны
            if filters.get("brand"):
                params["brand"] = filters["brand"]
            if filters.get("model_group"):
                params["model_group"] = filters["model_group"]
            if filters.get("model"):
                params["model"] = filters["model"]
            if filters.get("grade"):
                params["grade"] = filters["grade"]
            if filters.get("min_year"):
                params["min_year"] = filters["min_year"]
            if filters.get("max_year"):
                params["max_year"] = filters["max_year"]
            if filters.get("min_price"):
                params["min_price"] = filters["min_price"]
            if filters.get("max_price"):
                params["max_price"] = filters["max_price"]
            if filters.get("min_mileage"):
                params["min_mileage"] = filters["min_mileage"]
            if filters.get("max_mileage"):
                params["max_mileage"] = filters["max_mileage"]
            if filters.get("fuel"):
                params["fuel"] = filters["fuel"]
            if filters.get("transmission"):
                params["transmission"] = filters["transmission"]
            if filters.get("location"):
                params["location"] = filters["location"]

            response = await self.http_client.get(
                f"{self.base_url}/v2/dealers/web/cars/", params=params
            )

            if response.status_code == 200:
                cars_data = response.json()
                logger.info(f"Получено {len(cars_data)} автомобилей с фильтрами")
                return cars_data
            else:
                logger.error(f"Ошибка получения автомобилей: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Ошибка при получении автомобилей: {str(e)}")
            return []

    async def get_cars_with_auto_auth(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает автомобили с автоматической авторизацией

        Args:
            filters: Фильтры для поиска

        Returns:
            Список автомобилей
        """
        try:
            # Получаем действующую сессию
            headers, cookies = await heydealer_auth.get_headers_and_cookies_async()

            if not headers or not cookies:
                logger.error("Не удалось получить действующую сессию HeyDealer")
                return []

            # Подготавливаем параметры
            params = {
                "page": filters.get("page", 1) if filters else 1,
                "type": "auction",
                "is_subscribed": "false",
            }

            # Добавляем дополнительные фильтры
            if filters:
                for key, value in filters.items():
                    if key != "page" and value is not None:
                        params[key] = value

            # Выполняем запрос
            response = await self.http_client.get(
                url=f"{self.base_url}/v2/dealers/web/cars/",
                params=params,
                headers=headers,
                cookies=cookies,
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Получено {len(data)} автомобилей HeyDealer")
                return data
            elif response.status_code == 401:
                # Сессия устарела, пробуем обновить
                logger.warning("Сессия устарела, обновляем...")
                headers, cookies = await heydealer_auth.get_headers_and_cookies_async(
                    force_refresh=True
                )

                if headers and cookies:
                    response = await self.http_client.get(
                        url=f"{self.base_url}/v2/dealers/web/cars/",
                        params=params,
                        headers=headers,
                        cookies=cookies,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        logger.info(
                            f"✅ Получено {len(data)} автомобилей HeyDealer после обновления сессии"
                        )
                        return data

                logger.error("Не удалось авторизоваться в HeyDealer")
                return []
            else:
                logger.error(
                    f"Ошибка получения автомобилей HeyDealer: {response.status_code} - {response.text}"
                )
                return []

        except Exception as e:
            logger.error(f"Исключение при получении автомобилей HeyDealer: {e}")
            return []
