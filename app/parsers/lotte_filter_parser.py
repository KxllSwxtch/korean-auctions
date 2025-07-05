import json
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import re
from app.models.lotte_filters import (
    LotteManufacturer,
    LotteModel,
    LotteCarGroup,
    LotteMPriceCar,
    LotteCarResult,
    LotteSearchResponse,
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

    def parse_car_search_html(self, html_content: str) -> List[LotteCarResult]:
        """
        Парсинг HTML страницы с результатами поиска автомобилей

        Args:
            html_content: HTML контент страницы

        Returns:
            Список объектов LotteCarResult
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            cars = []

            # Находим основную таблицу с автомобилями
            main_table = soup.find("table", class_="tbl-t02")
            if not main_table:
                logger.warning("Не найдена основная таблица с автомобилями")
                return []

            # Находим все строки с данными автомобилей
            tbody = main_table.find("tbody")
            if not tbody:
                logger.warning("Не найден tbody в таблице автомобилей")
                return []

            rows = tbody.find_all("tr")
            logger.info(f"Найдено {len(rows)} строк с автомобилями")

            for row in rows:
                try:
                    car_data = self._parse_car_row(row)
                    if car_data:
                        cars.append(car_data)
                except Exception as e:
                    logger.error(f"Ошибка парсинга строки автомобиля: {e}")
                    continue

            logger.info(f"Успешно спарсено {len(cars)} автомобилей")
            return cars

        except Exception as e:
            logger.error(f"Ошибка парсинга HTML страницы: {e}")
            return []

    def _parse_car_row(self, row) -> Optional[LotteCarResult]:
        """
        Парсинг одной строки таблицы с автомобилем

        Args:
            row: BeautifulSoup элемент строки таблицы

        Returns:
            Объект LotteCarResult или None
        """
        try:
            cells = row.find_all("td")
            if len(cells) < 8:
                logger.warning(f"Недостаточно ячеек в строке: {len(cells)}")
                return None

            # Извлекаем данные из ячеек
            exhibition_number = cells[0].get_text(strip=True)
            lane = cells[1].get_text(strip=True)
            car_number = cells[2].get_text(strip=True)

            # Название автомобиля и ссылка на детали
            car_name_cell = cells[3]
            car_name_link = car_name_cell.find("a")
            car_name = (
                car_name_link.get_text(strip=True)
                if car_name_link
                else car_name_cell.get_text(strip=True)
            )

            # Извлекаем параметры для деталей из onclick
            detail_onclick = car_name_link.get("onclick", "") if car_name_link else ""
            car_id = self._extract_car_id_from_onclick(detail_onclick)

            year = cells[4].get_text(strip=True)
            mileage = cells[5].get_text(strip=True)
            color = cells[6].get_text(strip=True)
            grade = cells[7].get_text(strip=True)
            price = cells[8].get_text(strip=True) if len(cells) > 8 else None

            # Создаем объект автомобиля
            car_result = LotteCarResult(
                exhibition_number=exhibition_number,
                car_name=car_name,
                year=self._parse_year(year),
                mileage=mileage,
                grade=grade,
                lane=lane,
                start_price=self._parse_price(price),
                car_id=car_id,
                detail_url=(
                    f"/hp/auct/myp/entry/selectMypEntryCarDetPop.do?{car_id}"
                    if car_id
                    else None
                ),
                # Дополнительные поля
                transmission=self._extract_transmission(car_name),
                fuel_type=self._extract_fuel_type(car_name),
                location=color,  # Цвет как местоположение в данном контексте
            )

            return car_result

        except Exception as e:
            logger.error(f"Ошибка парсинга строки автомобиля: {e}")
            return None

    def _extract_car_id_from_onclick(self, onclick: str) -> Optional[str]:
        """
        Извлечение ID автомобиля из onclick атрибута

        Args:
            onclick: Строка с JavaScript кодом

        Returns:
            ID автомобиля или None
        """
        try:
            # Ищем паттерн fnPopupCarView("KS","KS202506300160","1")
            match = re.search(
                r'fnPopupCarView\("([^"]+)","([^"]+)","([^"]+)"\)', onclick
            )
            if match:
                mng_div_cd = match.group(1)
                mng_no = match.group(2)
                exhi_regi_seq = match.group(3)
                return f"searchMngDivCd={mng_div_cd}&searchMngNo={mng_no}&searchExhiRegiSeq={exhi_regi_seq}"
            return None
        except Exception as e:
            logger.error(f"Ошибка извлечения ID автомобиля: {e}")
            return None

    def _parse_year(self, year_str: str) -> Optional[int]:
        """
        Парсинг года выпуска

        Args:
            year_str: Строка с годом

        Returns:
            Год как число или None
        """
        try:
            if year_str and year_str.isdigit():
                return int(year_str)
            return None
        except Exception:
            return None

    def _parse_price(self, price_str: str) -> Optional[str]:
        """
        Парсинг цены

        Args:
            price_str: Строка с ценой

        Returns:
            Очищенная строка с ценой
        """
        try:
            if price_str:
                # Убираем HTML теги и лишние пробелы
                clean_price = re.sub(r"<[^>]+>", "", price_str)
                clean_price = re.sub(r"\s+", " ", clean_price).strip()
                return clean_price
            return None
        except Exception:
            return None

    def _extract_transmission(self, car_name: str) -> Optional[str]:
        """
        Извлечение типа трансмиссии из названия автомобиля

        Args:
            car_name: Название автомобиля

        Returns:
            Тип трансмиссии или None
        """
        try:
            if "AT" in car_name:
                return "AT"
            elif "MT" in car_name:
                return "MT"
            elif "CVT" in car_name:
                return "CVT"
            return None
        except Exception:
            return None

    def _extract_fuel_type(self, car_name: str) -> Optional[str]:
        """
        Извлечение типа топлива из названия автомобиля

        Args:
            car_name: Название автомобиля

        Returns:
            Тип топлива или None
        """
        try:
            if "TDI" in car_name or "DIESEL" in car_name.upper():
                return "Diesel"
            elif "HYBRID" in car_name.upper():
                return "Hybrid"
            elif "ELECTRIC" in car_name.upper() or "EV" in car_name:
                return "Electric"
            else:
                return "Gasoline"
        except Exception:
            return None

    def extract_total_count(self, html_content: str) -> int:
        """
        Извлечение общего количества автомобилей из HTML

        Args:
            html_content: HTML контент страницы

        Returns:
            Общее количество автомобилей
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Ищем текст с общим количеством
            total_text = soup.find(
                "span", string=lambda text: text and "대의 차량이 있습니다" in text
            )
            if total_text:
                # Извлекаем число из текста
                match = re.search(r"총 <em>(\d+)</em>대의", str(total_text.parent))
                if match:
                    return int(match.group(1))

            return 0
        except Exception as e:
            logger.error(f"Ошибка извлечения общего количества: {e}")
            return 0
