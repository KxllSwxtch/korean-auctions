"""
Сервис для работы с детальными страницами автомобилей Glovis
"""

import asyncio
from typing import Optional, Dict, Any
from urllib.parse import quote, unquote

from app.core.http_client import AsyncHttpClient
from app.parsers.glovis_detail_parser import GlovisDetailParser
from app.models.glovis_detail import (
    GlovisCarDetail,
    GlovisCarDetailResponse,
    GlovisCarDetailError,
)
from app.services.glovis_service import GlovisService
from app.core.logging import get_logger

logger = get_logger("glovis_detail_service")


class GlovisDetailService:
    """Сервис для получения детальной информации об автомобилях Glovis"""

    def __init__(self):
        self.glovis_service = GlovisService()
        self.parser = GlovisDetailParser()
        self.session = AsyncHttpClient()

        # Базовый URL для детальных страниц
        self.base_url = "https://auction.autobell.co.kr/auction/exhibitView.do"

        # Заголовки для запросов
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Referer": "https://auction.autobell.co.kr/auction/exhibitList.do",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    async def get_car_detail(
        self,
        car_id: str,
        auction_number: str = "747",
        acc: str = "30",
        rc: str = "1100",
    ) -> GlovisCarDetailResponse:
        """
        Получение детальной информации об автомобиле

        Args:
            car_id: ID автомобиля (параметр gn)
            auction_number: Номер аукциона (параметр atn)
            acc: Параметр acc
            rc: Параметр rc

        Returns:
            GlovisCarDetailResponse: Детальная информация об автомобиле
        """
        logger.info(f"🔍 Получение детальной информации об автомобиле: {car_id}")

        try:
            # Получаем актуальную сессию
            await self.glovis_service.ensure_valid_session()

            # Формируем URL с параметрами
            url = self._build_detail_url(car_id, auction_number, acc, rc)

            # Выполняем запрос
            response = await self._fetch_car_detail(url)

            if not response:
                return GlovisCarDetailResponse(
                    success=False, message="Не удалось получить данные автомобиля"
                )

            # Парсим полученные данные
            car_detail = self.parser.parse(response, url)

            logger.info(
                f"✅ Детальная информация получена: {car_detail.basic_info.name}"
            )

            return GlovisCarDetailResponse(
                success=True,
                message="Детальная информация успешно получена",
                data=car_detail,
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при получении детальной информации: {str(e)}")
            return GlovisCarDetailResponse(
                success=False, message=f"Ошибка при получении данных: {str(e)}"
            )

    async def get_car_detail_by_url(self, detail_url: str) -> GlovisCarDetailResponse:
        """
        Получение детальной информации об автомобиле по URL

        Args:
            detail_url: Полный URL детальной страницы

        Returns:
            GlovisCarDetailResponse: Детальная информация об автомобиле
        """
        logger.info(f"🔍 Получение детальной информации по URL: {detail_url}")

        try:
            # Получаем актуальную сессию
            await self.glovis_service.ensure_valid_session()

            # Выполняем запрос
            response = await self._fetch_car_detail(detail_url)

            if not response:
                return GlovisCarDetailResponse(
                    success=False, message="Не удалось получить данные автомобиля"
                )

            # Парсим полученные данные
            car_detail = self.parser.parse(response, detail_url)

            logger.info(
                f"✅ Детальная информация получена: {car_detail.basic_info.name}"
            )

            return GlovisCarDetailResponse(
                success=True,
                message="Детальная информация успешно получена",
                data=car_detail,
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при получении детальной информации: {str(e)}")
            return GlovisCarDetailResponse(
                success=False, message=f"Ошибка при получении данных: {str(e)}"
            )

    async def get_multiple_car_details(
        self, car_ids: list[str], auction_number: str = "747", max_concurrent: int = 5
    ) -> list[GlovisCarDetailResponse]:
        """
        Получение детальной информации о нескольких автомобилях

        Args:
            car_ids: Список ID автомобилей
            auction_number: Номер аукциона
            max_concurrent: Максимальное количество одновременных запросов

        Returns:
            list[GlovisCarDetailResponse]: Список детальных данных
        """
        logger.info(f"🔍 Получение детальной информации о {len(car_ids)} автомобилях")

        # Создаем семафор для ограничения количества одновременных запросов
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_single_car(car_id: str) -> GlovisCarDetailResponse:
            async with semaphore:
                return await self.get_car_detail(car_id, auction_number)

        # Выполняем запросы параллельно
        tasks = [fetch_single_car(car_id) for car_id in car_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обрабатываем результаты
        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"❌ Ошибка при получении данных для {car_ids[i]}: {str(result)}"
                )
                responses.append(
                    GlovisCarDetailResponse(
                        success=False, message=f"Ошибка: {str(result)}"
                    )
                )
            else:
                responses.append(result)

        successful_count = sum(1 for r in responses if r.success)
        logger.info(
            f"✅ Успешно получено {successful_count} из {len(car_ids)} автомобилей"
        )

        return responses

    async def _fetch_car_detail(self, url: str) -> Optional[str]:
        """
        Получение HTML страницы автомобиля

        Args:
            url: URL страницы автомобиля

        Returns:
            Optional[str]: HTML контент или None в случае ошибки
        """
        try:
            # Получаем актуальные cookies
            cookies = self.glovis_service.get_current_cookies()

            logger.debug(f"🌐 Запрос к URL: {url}")

            # Выполняем запрос
            response = await self.session.get(
                url=url, headers=self.headers, cookies=cookies, timeout=30
            )

            if response.status_code == 200:
                logger.debug("✅ Успешно получен HTML контент")
                return response.text
            else:
                logger.error(
                    f"❌ Ошибка HTTP {response.status_code}: {response.text[:200]}"
                )
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка при запросе: {str(e)}")
            return None

    def _build_detail_url(
        self, car_id: str, auction_number: str, acc: str, rc: str
    ) -> str:
        """
        Построение URL для детальной страницы автомобиля

        Args:
            car_id: ID автомобиля
            auction_number: Номер аукциона
            acc: Параметр acc
            rc: Параметр rc

        Returns:
            str: Полный URL
        """
        # Кодируем car_id, если он не закодирован
        if not self._is_url_encoded(car_id):
            car_id = quote(car_id)

        params = {"acc": acc, "gn": car_id, "rc": rc, "atn": auction_number}

        # Формируем строку параметров
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])

        url = f"{self.base_url}?{param_string}"
        logger.debug(f"🔗 Сформирован URL: {url}")

        return url

    def _is_url_encoded(self, text: str) -> bool:
        """
        Проверка, является ли строка URL-кодированной

        Args:
            text: Проверяемая строка

        Returns:
            bool: True, если строка уже закодирована
        """
        try:
            # Если после декодирования строка изменилась, значит она была закодирована
            return unquote(text) != text
        except:
            return False

    async def validate_car_detail(self, car_detail: GlovisCarDetail) -> Dict[str, Any]:
        """
        Валидация полученных данных автомобиля

        Args:
            car_detail: Данные автомобиля для валидации

        Returns:
            Dict[str, Any]: Результат валидации
        """
        validation_result = {
            "is_valid": True,
            "issues": [],
            "completeness_score": 0,
            "data_quality": "good",
        }

        # Проверяем обязательные поля
        if not car_detail.basic_info.name:
            validation_result["issues"].append("Отсутствует название автомобиля")
            validation_result["is_valid"] = False

        if not car_detail.basic_info.manufacturer:
            validation_result["issues"].append("Отсутствует производитель")

        if not car_detail.basic_info.model:
            validation_result["issues"].append("Отсутствует модель")

        # Проверяем ключевые характеристики
        if not car_detail.basic_info.mileage:
            validation_result["issues"].append("Отсутствует пробег")

        if not car_detail.basic_info.year:
            validation_result["issues"].append("Отсутствует год выпуска")

        # Проверяем изображения
        if not car_detail.images:
            validation_result["issues"].append("Отсутствуют изображения")

        # Рассчитываем полноту данных
        total_fields = 20  # Примерное количество важных полей
        filled_fields = 0

        if car_detail.basic_info.name:
            filled_fields += 1
        if car_detail.basic_info.manufacturer:
            filled_fields += 1
        if car_detail.basic_info.model:
            filled_fields += 1
        if car_detail.basic_info.year:
            filled_fields += 1
        if car_detail.basic_info.mileage:
            filled_fields += 1
        if car_detail.basic_info.fuel_type:
            filled_fields += 1
        if car_detail.basic_info.transmission:
            filled_fields += 1
        if car_detail.basic_info.color:
            filled_fields += 1
        if car_detail.pricing:
            filled_fields += 1
        if car_detail.detailed_specs:
            filled_fields += 1
        if car_detail.performance_check:
            filled_fields += 1
        if car_detail.options:
            filled_fields += 1
        if car_detail.images:
            filled_fields += 1

        validation_result["completeness_score"] = (filled_fields / total_fields) * 100

        # Определяем качество данных
        if validation_result["completeness_score"] >= 80:
            validation_result["data_quality"] = "excellent"
        elif validation_result["completeness_score"] >= 60:
            validation_result["data_quality"] = "good"
        elif validation_result["completeness_score"] >= 40:
            validation_result["data_quality"] = "fair"
        else:
            validation_result["data_quality"] = "poor"

        return validation_result

    async def close(self):
        """Закрытие соединений"""
        await self.session.close()

    def __del__(self):
        """Деструктор для очистки ресурсов"""
        try:
            import asyncio

            if hasattr(self, "session"):
                asyncio.create_task(self.session.close())
        except:
            pass
