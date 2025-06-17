import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
from datetime import datetime
import logging

from app.models.autohub import (
    AutohubCar,
    CarStatus,
    TransmissionType,
    FuelType,
    AutohubAuctionDate,
    AutohubCarDetail,
    AutohubPerformanceInfo,
    AutohubOptionInfo,
    AutohubImage,
)
from app.core.logging import get_logger

logger = logging.getLogger(__name__)


class AutohubParser:
    """Парсер для Autohub auction"""

    def __init__(self, base_url: str = "https://www.autohubauction.co.kr"):
        self.base_url = base_url

    def parse_car_list(self, html_content: str) -> List[AutohubCar]:
        """
        Парсит HTML страницу и извлекает список автомобилей

        Args:
            html_content: HTML контент страницы

        Returns:
            List[AutohubCar]: Список автомобилей
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            cars = []

            # Ищем все блоки с автомобилями
            car_blocks = soup.find_all("div", class_="car_one")

            logger.info(f"Найдено {len(car_blocks)} блоков автомобилей")

            for block in car_blocks:
                try:
                    car_data = self._parse_single_car(block)
                    if car_data:
                        cars.append(car_data)
                except Exception as e:
                    logger.error(f"Ошибка при парсинге автомобиля: {e}")
                    continue

            logger.info(f"Успешно спарсено {len(cars)} автомобилей")
            return cars

        except Exception as e:
            logger.error(f"Ошибка при парсинге списка автомобилей: {e}")
            return []

    def _parse_single_car(self, car_block: Tag) -> Optional[AutohubCar]:
        """
        Парсит информацию об одном автомобиле

        Args:
            car_block: BeautifulSoup элемент с информацией об автомобиле

        Returns:
            AutohubCar: Данные об автомобиле
        """
        try:
            # Извлекаем car_id из onclick атрибута
            car_id = self._extract_car_id(car_block)
            if not car_id:
                logger.warning("Не удалось извлечь car_id")
                return None

            # Основная информация об автомобиле
            title = self._extract_title(car_block)
            if not title:
                logger.warning(f"Не удалось извлечь название для car_id: {car_id}")
                return None

            # Извлекаем остальную информацию
            car_info = self._extract_car_info(car_block)
            identifiers = self._extract_identifiers(car_block)
            financial_info = self._extract_financial_info(car_block)
            status_info = self._extract_status_info(car_block)
            image_url = self._extract_main_image(car_block)

            # Создаем объект автомобиля
            car = AutohubCar(
                car_id=car_id,
                title=title,
                # Идентификаторы
                auction_number=identifiers.get("auction_number", ""),
                car_number=identifiers.get("car_number", ""),
                parking_number=identifiers.get("parking_number", ""),
                lane=identifiers.get("lane"),
                # Основная информация
                year=car_info.get("year", 0),
                mileage=car_info.get("mileage", ""),
                transmission=car_info.get("transmission", TransmissionType.AUTO),
                fuel_type=car_info.get("fuel_type", FuelType.GASOLINE),
                # Дополнительная информация
                first_registration_date=car_info.get("first_registration_date"),
                condition_grade=car_info.get("condition_grade"),
                history=car_info.get("history"),
                # Финансовая информация
                starting_price=financial_info.get("starting_price"),
                current_price=financial_info.get("current_price"),
                final_price=financial_info.get("final_price"),
                # Статус
                status=status_info.get("status", CarStatus.REGISTERED),
                auction_result=status_info.get("auction_result"),
                # Изображения
                main_image_url=image_url,
                additional_images=[],
            )

            return car

        except Exception as e:
            logger.error(f"Ошибка при парсинге автомобиля: {e}")
            return None

    def _extract_car_id(self, car_block: Tag) -> Optional[str]:
        """Извлекает car_id из onclick атрибута"""
        try:
            # Ищем ссылку с onclick
            link = car_block.find("a", onclick=re.compile(r"carInfo\('([^']+)'\)"))
            if link and link.get("onclick"):
                match = re.search(r"carInfo\('([^']+)'\)", link["onclick"])
                if match:
                    return match.group(1)
        except Exception as e:
            logger.error(f"Ошибка при извлечении car_id: {e}")
        return None

    def _extract_title(self, car_block: Tag) -> Optional[str]:
        """Извлекает название автомобиля"""
        try:
            title_element = car_block.find("div", class_="car-title")
            if title_element:
                link = title_element.find("a")
                if link:
                    return link.get_text(strip=True)
        except Exception as e:
            logger.error(f"Ошибка при извлечении title: {e}")
        return None

    def _extract_car_info(self, car_block: Tag) -> Dict[str, Any]:
        """Извлекает основную информацию об автомобиле"""
        info = {}

        try:
            # Ищем список с основной информацией
            car_list = car_block.find("ul", class_="list-inline")
            if car_list:
                items = car_list.find_all("li")
                if len(items) >= 4:
                    # Год
                    year_text = items[0].get_text(strip=True)
                    if year_text.isdigit():
                        info["year"] = int(year_text)

                    # Пробег
                    info["mileage"] = items[1].get_text(strip=True)

                    # Трансмиссия
                    transmission_text = items[2].get_text(strip=True)
                    info["transmission"] = self._parse_transmission(transmission_text)

                    # Тип топлива
                    fuel_text = items[3].get_text(strip=True)
                    info["fuel_type"] = self._parse_fuel_type(fuel_text)

            # Дополнительная информация из других элементов
            # Дата регистрации
            reg_date_element = car_block.find("strong", string="최초등록일 : ")
            if reg_date_element and reg_date_element.next_sibling:
                info["first_registration_date"] = reg_date_element.next_sibling.strip()

            # Оценка состояния
            grade_element = car_block.find("strong", string="평가점 : ")
            if grade_element and grade_element.next_sibling:
                info["condition_grade"] = grade_element.next_sibling.strip()

            # История использования
            history_element = car_block.find("strong", string="경력 : ")
            if history_element and history_element.next_sibling:
                info["history"] = history_element.next_sibling.strip()

        except Exception as e:
            logger.error(f"Ошибка при извлечении car_info: {e}")

        return info

    def _extract_identifiers(self, car_block: Tag) -> Dict[str, str]:
        """Извлекает идентификаторы автомобиля"""
        identifiers = {}

        try:
            # Номер лота
            auction_num_element = car_block.find("strong", string="출품번호 : ")
            if auction_num_element:
                next_strong = auction_num_element.find_next("strong")
                if next_strong:
                    font_element = next_strong.find("font")
                    if font_element:
                        identifiers["auction_number"] = font_element.get_text(
                            strip=True
                        )

            # Номер автомобиля
            car_num_element = car_block.find("strong", string="차량번호 : ")
            if car_num_element and car_num_element.next_sibling:
                identifiers["car_number"] = car_num_element.next_sibling.strip()

            # Номер парковки
            parking_element = car_block.find("strong", string="주차번호 : ")
            if parking_element:
                next_strong = parking_element.find_next("strong")
                if next_strong:
                    font_element = next_strong.find("font")
                    if font_element:
                        identifiers["parking_number"] = font_element.get_text(
                            strip=True
                        )

            # Полоса
            lane_element = car_block.find("strong", string="레인 : ")
            if lane_element and lane_element.next_sibling:
                lane_text = lane_element.next_sibling.strip()
                if lane_text:
                    identifiers["lane"] = lane_text

        except Exception as e:
            logger.error(f"Ошибка при извлечении identifiers: {e}")

        return identifiers

    def _extract_financial_info(self, car_block: Tag) -> Dict[str, Optional[int]]:
        """Извлекает финансовую информацию"""
        financial = {}

        try:
            # Стартовая цена
            price_element = car_block.find("strong", string="시작가 : ")
            if price_element:
                next_strong = price_element.find_next("strong")
                if next_strong:
                    price_text = next_strong.get_text(strip=True).replace(",", "")
                    if price_text.isdigit():
                        financial["starting_price"] = int(price_text)

        except Exception as e:
            logger.error(f"Ошибка при извлечении financial_info: {e}")

        return financial

    def _extract_status_info(self, car_block: Tag) -> Dict[str, Any]:
        """Извлекает информацию о статусе"""
        status_info = {}

        try:
            # Статус
            status_element = car_block.find("strong", string="진행상태 : ")
            if status_element and status_element.next_sibling:
                status_text = status_element.next_sibling.strip()
                status_info["status"] = self._parse_status(status_text)

            # Результат аукциона
            result_element = car_block.find("strong", string="경매결과 : ")
            if result_element and result_element.next_sibling:
                result_text = result_element.next_sibling.strip()
                if result_text != "-":
                    status_info["auction_result"] = result_text

        except Exception as e:
            logger.error(f"Ошибка при извлечении status_info: {e}")

        return status_info

    def _extract_main_image(self, car_block: Tag) -> Optional[str]:
        """Извлекает URL основного изображения"""
        try:
            img_element = car_block.find("img", class_="img-fluid")
            if img_element and img_element.get("src"):
                src = img_element["src"]
                # Если URL относительный, делаем его абсолютным
                if src.startswith("/"):
                    return f"{self.base_url}{src}"
                return src
        except Exception as e:
            logger.error(f"Ошибка при извлечении main_image: {e}")
        return None

    def _parse_transmission(self, text: str) -> TransmissionType:
        """Парсит тип трансмиссии"""
        if "오토" in text:
            return TransmissionType.AUTO
        elif "수동" in text:
            return TransmissionType.MANUAL
        return TransmissionType.AUTO

    def _parse_fuel_type(self, text: str) -> FuelType:
        """Парсит тип топлива"""
        if "경유" in text:
            return FuelType.DIESEL
        elif "휘발유" in text:
            return FuelType.GASOLINE
        elif "전기" in text:
            return FuelType.ELECTRIC
        elif "하이브리드" in text:
            return FuelType.HYBRID
        return FuelType.GASOLINE

    def _parse_status(self, text: str) -> CarStatus:
        """Парсит статус автомобиля"""
        if "출품등록" in text:
            return CarStatus.REGISTERED
        elif "입찰중" in text:
            return CarStatus.BIDDING
        elif "낙찰" in text:
            return CarStatus.SOLD
        elif "유찰" in text:
            return CarStatus.UNSOLD
        elif "취하" in text:
            return CarStatus.WITHDRAWN
        return CarStatus.REGISTERED


def parse_auction_date(html: str) -> Optional[AutohubAuctionDate]:
    """Парсинг даты аукциона из HTML"""
    soup = BeautifulSoup(html, "html.parser")

    try:
        # Поиск даты аукциона на странице
        date_elements = soup.find_all(
            ["span", "div", "td"], string=re.compile(r"\d{4}\.\d{2}\.\d{2}")
        )

        if date_elements:
            date_text = date_elements[0].get_text().strip()
            return AutohubAuctionDate(date_str=date_text)

        return None
    except Exception as e:
        logger.error(f"Ошибка при парсинге даты аукциона: {e}")
        return None


def parse_car_detail(html: str) -> Optional[AutohubCarDetail]:
    """Парсинг детальной информации об автомобиле"""
    soup = BeautifulSoup(html, "html.parser")

    try:
        # Парсинг основной информации
        title = parse_car_title(soup)
        starting_price = parse_starting_price(soup)
        auction_info = parse_auction_info(soup)

        # Парсинг детальной информации об автомобиле
        car_info = parse_car_info(soup)

        # Парсинг информации о производительности
        performance_info = parse_performance_info(soup)

        # Парсинг опций
        options = parse_options(soup)

        # Парсинг изображений
        images = parse_images(soup)

        return AutohubCarDetail(
            title=title,
            starting_price=starting_price,
            auction_number=auction_info.get("auction_number", ""),
            auction_date=auction_info.get("auction_date", ""),
            auction_title=auction_info.get("auction_title", ""),
            auction_code=auction_info.get("auction_code", ""),
            car_info=car_info,
            performance_info=performance_info,
            options=options,
            images=images,
            parsed_at=datetime.now(),
        )

    except Exception as e:
        logger.error(f"Ошибка при парсинге детальной информации: {e}")
        return None


def parse_car_title(soup: BeautifulSoup) -> str:
    """Парсинг заголовка автомобиля"""
    try:
        title_element = soup.find("h2", class_="tit_style2")
        if title_element:
            return title_element.get_text().strip()
        return ""
    except Exception as e:
        logger.error(f"Ошибка при парсинге заголовка: {e}")
        return ""


def parse_starting_price(soup: BeautifulSoup) -> str:
    """Парсинг стартовой цены"""
    try:
        price_element = soup.find("strong", class_="i_comm_main_txt2")
        if price_element:
            return price_element.get_text().strip()
        return "0"
    except Exception as e:
        logger.error(f"Ошибка при парсинге цены: {e}")
        return "0"


def parse_auction_info(soup: BeautifulSoup) -> Dict[str, str]:
    """Парсинг информации об аукционе"""
    auction_info = {
        "auction_number": "",
        "auction_date": "",
        "auction_title": "",
        "auction_code": "",
    }

    try:
        # Поиск скрытых полей с информацией об аукционе
        hidden_inputs = soup.find_all("input", type="hidden")

        for input_elem in hidden_inputs:
            name = input_elem.get("name", "")
            value = input_elem.get("value", "")

            if "AucNo" in name:
                auction_info["auction_number"] = value
            elif "StartDt" in name:
                auction_info["auction_date"] = value
            elif "AucTitle" in name:
                auction_info["auction_title"] = value
            elif "AucCode" in name:
                auction_info["auction_code"] = value

    except Exception as e:
        logger.error(f"Ошибка при парсинге информации об аукционе: {e}")

    return auction_info


def parse_car_info(soup: BeautifulSoup) -> AutohubCar:
    """Парсинг детальной информации об автомобиле"""
    car_info = {}

    try:
        # Поиск блока с информацией об автомобиле
        details_block = soup.find("div", class_="details-block")
        if not details_block:
            raise ValueError("Блок с деталями автомобиля не найден")

        # Парсинг всех строк с информацией
        list_items = details_block.find_all("li")

        for item in list_items:
            span = item.find("span")
            strong = item.find("strong")

            if span and strong:
                label = span.get_text().strip()
                value = strong.get_text().strip()

                # Обработка специальных случаев
                if "출품번호" in label:
                    car_info["entry_number"] = value
                elif "주차번호" in label:
                    car_info["parking_number"] = value
                elif "차량번호" in label:
                    car_info["car_number"] = value
                elif "차대번호" in label:
                    car_info["vin_number"] = value
                elif "연식" in label:
                    # Парсинг года и даты первой регистрации
                    year_match = re.search(r"(\d{4})", value)
                    reg_match = re.search(r"최초등록일\s*:\s*(\d{8})", value)

                    car_info["year"] = year_match.group(1) if year_match else value
                    if reg_match:
                        car_info["first_registration"] = reg_match.group(1)
                elif "원동기형식" in label:
                    car_info["engine_type"] = value
                elif "연료" in label:
                    car_info["fuel_type"] = value
                elif "주행거리" in label:
                    # Проверка на неопределенность пробега
                    mileage_unclear = "불분명" in value
                    mileage = re.sub(r"[^\d,]", "", value.split("(")[0])

                    car_info["mileage"] = mileage
                    car_info["mileage_unclear"] = mileage_unclear
                elif "배기량" in label:
                    car_info["displacement"] = value
                elif "경력" in label:
                    car_info["history"] = value
                elif "변속기" in label:
                    car_info["transmission"] = value
                elif "색상" in label:
                    # Проверка на изменение цвета
                    color_changed = "색상변경" in value
                    color = value.split("(")[0].strip()

                    car_info["color"] = color
                    car_info["color_changed"] = color_changed
                elif "차종" in label:
                    car_info["vehicle_type"] = value
                elif "사고이력" in label:
                    car_info["accident_history"] = value
                elif "과세구분" in label:
                    car_info["tax_type"] = value
                elif "전기차 인증서" in label:
                    car_info["electric_certificate"] = value

        # Установка значений по умолчанию для обязательных полей
        required_fields = {
            "entry_number": "",
            "parking_number": "",
            "car_number": "",
            "vin_number": "",
            "year": "",
            "engine_type": "",
            "fuel_type": "",
            "mileage": "",
            "displacement": "",
            "history": "",
            "transmission": "",
            "color": "",
            "vehicle_type": "",
            "tax_type": "",
        }

        for field, default_value in required_fields.items():
            if field not in car_info:
                car_info[field] = default_value

        # Добавляем обязательные поля для модели AutohubCar
        car_info["car_id"] = car_info.get("entry_number", "") or "unknown"
        car_info["auction_number"] = car_info.get("entry_number", "") or "unknown"
        car_info["title"] = (
            f"{car_info.get('year', '')} {car_info.get('engine_type', '')} {car_info.get('fuel_type', '')}"
        )

        # Обработка года
        year_str = car_info.get("year", "2000")
        try:
            car_info["year"] = int(year_str) if year_str.isdigit() else 2000
        except (ValueError, AttributeError):
            car_info["year"] = 2000

        # Обработка трансмиссии
        transmission = car_info.get("transmission", "").strip()
        if transmission in ["오토", "자동"]:
            car_info["transmission"] = TransmissionType.AUTO
        elif transmission in ["수동", "매뉴얼"]:
            car_info["transmission"] = TransmissionType.MANUAL
        else:
            car_info["transmission"] = TransmissionType.AUTO  # default

        # Обработка топлива
        fuel = car_info.get("fuel_type", "").strip()
        if "휘발유" in fuel or "가솔린" in fuel:
            car_info["fuel_type"] = FuelType.GASOLINE
        elif "경유" in fuel or "디젤" in fuel:
            car_info["fuel_type"] = FuelType.DIESEL
        elif "전기" in fuel:
            car_info["fuel_type"] = FuelType.ELECTRIC
        elif "하이브리드" in fuel:
            car_info["fuel_type"] = FuelType.HYBRID
        else:
            car_info["fuel_type"] = FuelType.GASOLINE  # default

        # Статус по умолчанию
        car_info["status"] = CarStatus.REGISTERED

        return AutohubCar(**car_info)

    except Exception as e:
        logger.error(f"Ошибка при парсинге информации об автомобиле: {e}")
        # Возвращаем объект с пустыми значениями
        return AutohubCar(
            car_id="unknown",
            auction_number="unknown",
            car_number="",
            parking_number="",
            lane=None,
            title="Unknown Car",
            year=2000,
            mileage="0",
            transmission=TransmissionType.AUTO,
            fuel_type=FuelType.GASOLINE,
            status=CarStatus.REGISTERED,
            entry_number="",
            vin_number="",
            engine_type="",
            displacement="",
            history="",
            color="",
            vehicle_type="",
            tax_type="",
        )


def parse_performance_info(soup: BeautifulSoup) -> AutohubPerformanceInfo:
    """Парсинг информации о производительности"""
    try:
        # Поиск таблицы с информацией о производительности
        perf_table = soup.find("table", class_="tabl_3")
        if not perf_table:
            raise ValueError("Таблица с оценкой производительности не найдена")

        rating = ""
        inspector = ""
        stored_items = []
        stored_items_present = ""
        notes = ""

        rows = perf_table.find_all("tr")

        for row in rows:
            th = row.find("th")
            td = row.find("td")

            if th and td:
                label = th.get_text().strip()
                value = td.get_text().strip()

                if "평가점" in label:
                    rating = value
                elif "점검원" in label:
                    inspector = value
                elif "보관물품" in label:
                    # Парсинг отмеченных предметов
                    checkboxes = td.find_all("input", {"type": "checkbox"})
                    for checkbox in checkboxes:
                        if checkbox.get("checked"):
                            title = checkbox.get("title", "")
                            if title:
                                stored_items.append(title)
                elif "보관품 여부" in label:
                    stored_items_present = value
                elif "비고" in label:
                    notes = value

        return AutohubPerformanceInfo(
            rating=rating,
            inspector=inspector,
            stored_items=stored_items,
            stored_items_present=stored_items_present,
            notes=notes,
        )

    except Exception as e:
        logger.error(f"Ошибка при парсинге информации о производительности: {e}")
        return AutohubPerformanceInfo(
            rating="", inspector="", stored_items=[], stored_items_present="", notes=""
        )


def parse_options(soup: BeautifulSoup) -> AutohubOptionInfo:
    """Парсинг опций автомобиля"""
    try:
        # Поиск таблицы с опциями
        option_table = soup.find("table", class_="tabl_3 tabl_3_tb_th keepStuff")
        if not option_table:
            raise ValueError("Таблица с опциями не найдена")

        convenience = []
        safety = []
        exterior = []
        interior = []

        rows = option_table.find_all("tr")

        for row in rows:
            th = row.find("th")
            td = row.find("td")

            if th and td:
                category = th.get_text().strip()

                # Парсинг отмеченных опций
                checkboxes = td.find_all("input", {"type": "checkbox"})
                options_list = []

                for checkbox in checkboxes:
                    if checkbox.get("checked"):
                        title = checkbox.get("title", "")
                        if title:
                            options_list.append(title)

                # Распределение по категориям
                if "편의" in category:
                    convenience = options_list
                elif "안전" in category:
                    safety = options_list
                elif "외관" in category:
                    exterior = options_list
                elif "내장" in category:
                    interior = options_list

        return AutohubOptionInfo(
            convenience=convenience, safety=safety, exterior=exterior, interior=interior
        )

    except Exception as e:
        logger.error(f"Ошибка при парсинге опций: {e}")
        return AutohubOptionInfo(convenience=[], safety=[], exterior=[], interior=[])


def parse_images(soup: BeautifulSoup) -> List[AutohubImage]:
    """Парсинг изображений автомобиля"""
    images = []

    try:
        # Поиск больших изображений
        large_images = soup.find_all("img", class_="carImg")

        for i, img in enumerate(large_images):
            large_url = img.get("src", "")
            if large_url:
                # Получение URL маленького изображения
                small_url = large_url.replace("_L.jpg", "_S.jpg")

                images.append(
                    AutohubImage(large_url=large_url, small_url=small_url, sequence=i)
                )

    except Exception as e:
        logger.error(f"Ошибка при парсинге изображений: {e}")

    return images
