import json
from typing import List, Dict, Any, Optional
from app.models.lotte_filters import (
    LotteManufacturer,
    LotteModel,
    LotteCarGroup,
    LotteMPriceCar,
)
from app.core.logging import logger


class LotteFilterParser:
    """Парсер для фильтров Lotte"""

    def parse_manufacturers(self, json_response: str) -> List[LotteManufacturer]:
        """
        Парсинг списка производителей из JSON ответа

        Args:
            json_response: JSON ответ от API Lotte

        Returns:
            Список объектов LotteManufacturer
        """
        try:
            data = (
                json.loads(json_response)
                if isinstance(json_response, str)
                else json_response
            )

            if not isinstance(data, dict) or "result" not in data:
                logger.error("Неверный формат ответа для производителей")
                return []

            manufacturers = []
            for item in data["result"]:
                if isinstance(item, dict) and "code" in item and "name" in item:
                    manufacturer = LotteManufacturer(
                        code=item["code"], name=item["name"]
                    )
                    manufacturers.append(manufacturer)

            logger.info(f"Спарсено {len(manufacturers)} производителей")
            return manufacturers

        except Exception as e:
            logger.error(f"Ошибка парсинга производителей: {e}")
            return []

    def parse_models(
        self, json_response: str, manufacturer_code: Optional[str] = None
    ) -> List[LotteModel]:
        """
        Парсинг списка моделей из JSON ответа

        Args:
            json_response: JSON ответ от API Lotte
            manufacturer_code: Код производителя для связи

        Returns:
            Список объектов LotteModel
        """
        try:
            data = (
                json.loads(json_response)
                if isinstance(json_response, str)
                else json_response
            )

            if not isinstance(data, dict) or "result" not in data:
                logger.error("Неверный формат ответа для моделей")
                return []

            models = []
            for item in data["result"]:
                if isinstance(item, dict) and "code" in item and "name" in item:
                    model = LotteModel(
                        code=item["code"],
                        name=item["name"],
                        manufacturer_code=manufacturer_code,
                    )
                    models.append(model)

            logger.info(
                f"Спарсено {len(models)} моделей для производителя {manufacturer_code}"
            )
            return models

        except Exception as e:
            logger.error(f"Ошибка парсинга моделей: {e}")
            return []

    def parse_car_groups(
        self, json_response: str, model_code: Optional[str] = None
    ) -> List[LotteCarGroup]:
        """
        Парсинг списка групп автомобилей из JSON ответа

        Args:
            json_response: JSON ответ от API Lotte
            model_code: Код модели для связи

        Returns:
            Список объектов LotteCarGroup
        """
        try:
            data = (
                json.loads(json_response)
                if isinstance(json_response, str)
                else json_response
            )

            if not isinstance(data, dict) or "result" not in data:
                logger.error("Неверный формат ответа для групп автомобилей")
                return []

            car_groups = []
            for item in data["result"]:
                if isinstance(item, dict) and "code" in item and "name" in item:
                    car_group = LotteCarGroup(
                        code=item["code"], name=item["name"], model_code=model_code
                    )
                    car_groups.append(car_group)

            logger.info(
                f"Спарсено {len(car_groups)} групп автомобилей для модели {model_code}"
            )
            return car_groups

        except Exception as e:
            logger.error(f"Ошибка парсинга групп автомобилей: {e}")
            return []

    def parse_mprice_cars(
        self, json_response: str, car_group_code: Optional[str] = None
    ) -> List[LotteMPriceCar]:
        """
        Парсинг списка подмоделей с ценами из JSON ответа

        Args:
            json_response: JSON ответ от API Lotte
            car_group_code: Код группы автомобилей для связи

        Returns:
            Список объектов LotteMPriceCar
        """
        try:
            data = (
                json.loads(json_response)
                if isinstance(json_response, str)
                else json_response
            )

            if not isinstance(data, dict) or "result" not in data:
                logger.error("Неверный формат ответа для подмоделей")
                return []

            mprice_cars = []
            for item in data["result"]:
                if isinstance(item, dict) and "code" in item and "name" in item:
                    mprice_car = LotteMPriceCar(
                        code=item["code"],
                        name=item["name"],
                        car_group_code=car_group_code,
                    )
                    mprice_cars.append(mprice_car)

            logger.info(
                f"Спарсено {len(mprice_cars)} подмоделей для группы {car_group_code}"
            )
            return mprice_cars

        except Exception as e:
            logger.error(f"Ошибка парсинга подмоделей: {e}")
            return []

    def validate_filter_data(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Валидация и нормализация данных фильтра

        Args:
            filters: Словарь с параметрами фильтра

        Returns:
            Нормализованный словарь фильтров
        """
        try:
            normalized = {}

            # Обязательные поля для поиска
            if "searchFlag" in filters:
                normalized["searchFlag"] = filters["searchFlag"]

            if "searchCode" in filters:
                normalized["searchCode"] = filters["searchCode"]

            # Дополнительные параметры поиска
            if "search_doimCd" in filters:
                normalized["search_doimCd"] = filters.get("search_doimCd", "")

            logger.info(f"Нормализованы фильтры: {normalized}")
            return normalized

        except Exception as e:
            logger.error(f"Ошибка валидации фильтров: {e}")
            return {}

    def build_search_data(self, filter_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Построение данных для поискового запроса

        Args:
            filter_request: Параметры фильтрации

        Returns:
            Данные для POST запроса
        """
        try:
            data = {
                "searchPageUnit": str(filter_request.get("per_page", 20)),
                "pageIndex": str(filter_request.get("page", 1)),
                "search_grntVal": filter_request.get("search_grntVal", ""),
                "search_concVal": filter_request.get("search_concVal", ""),
                "search_preVal": filter_request.get("search_preVal", ""),
                "excelDiv": "",
                "searchLaneDiv": filter_request.get("lane_division", ""),
                "search_doimCd": filter_request.get("search_doimCd", ""),
                "search_exhiNo": filter_request.get("exhibition_number", ""),
                "search_fuelCd": filter_request.get("fuel_code", ""),
                "search_trnsCd": filter_request.get("transmission_code", ""),
            }

            # Производитель и модель
            if filter_request.get("manufacturer_code"):
                data["set_search_maker"] = filter_request["manufacturer_code"]

            if filter_request.get("model_code"):
                data["set_search_mdl"] = filter_request["model_code"]

            # Дата аукциона
            if filter_request.get("auction_date"):
                data["searchAuctDt"] = filter_request["auction_date"]

            # Ценовые фильтры
            if filter_request.get("min_price"):
                data["search_startPrice"] = str(filter_request["min_price"])
                data["search_startPrice_s"] = str(filter_request["min_price"])

            if filter_request.get("max_price"):
                data["search_endPrice"] = str(filter_request["max_price"])
                data["search_endPrice_s"] = str(filter_request["max_price"])

            # Год выпуска
            if filter_request.get("min_year"):
                data["search_startYyyy"] = str(filter_request["min_year"])

            if filter_request.get("max_year"):
                data["search_endYyyy"] = str(filter_request["max_year"])

            # Группы автомобилей
            if filter_request.get("car_group_codes"):
                for code in filter_request["car_group_codes"]:
                    data["set_search_chk_carGrp"] = code

            # Подмодели
            if filter_request.get("mprice_car_codes"):
                data["set_search_chk_mpriceCar"] = filter_request["mprice_car_codes"]

            logger.info(f"Построены данные поиска: {data}")
            return data

        except Exception as e:
            logger.error(f"Ошибка построения данных поиска: {e}")
            return {}
