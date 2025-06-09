import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin

from app.models.autohub import AutohubCar, CarStatus, TransmissionType, FuelType
from app.core.logging import get_logger

logger = get_logger("autohub_parser")


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
                return img_element["src"]
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
