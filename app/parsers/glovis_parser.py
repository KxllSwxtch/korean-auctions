import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag

from app.models.glovis import (
    GlovisCar,
    GlovisResponse,
    GlovisLocation,
    GlovisCarCondition,
)
from app.core.logging import get_logger

logger = get_logger("glovis_parser")


class GlovisParser:
    """Парсер HTML данных аукциона Hyundai Glovis"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def parse_car_list(self, html_content: str, page: int = 1) -> GlovisResponse:
        """
        Парсит HTML страницу со списком автомобилей

        Args:
            html_content: HTML содержимое страницы
            page: Номер текущей страницы

        Returns:
            GlovisResponse: Объект с распарсенными данными
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Извлекаем общее количество автомобилей
            total_count = self._extract_total_count(soup)

            # Извлекаем список автомобилей
            cars = self._extract_cars(soup)

            # Вычисляем пагинацию
            page_size = 18  # По умолчанию Glovis показывает 18 автомобилей на странице
            total_pages = (
                (total_count + page_size - 1) // page_size if total_count > 0 else 1
            )
            has_next_page = page < total_pages
            has_prev_page = page > 1

            return GlovisResponse(
                success=True,
                message=f"Успешно загружено {len(cars)} автомобилей из {total_count}",
                total_count=total_count,
                cars=cars,
                current_page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next_page=has_next_page,
                has_prev_page=has_prev_page,
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге списка автомобилей: {e}")
            return GlovisResponse(
                success=False,
                message=f"Ошибка парсинга: {str(e)}",
                total_count=0,
                cars=[],
            )

    def _extract_total_count(self, soup: BeautifulSoup) -> int:
        """Извлекает общее количество автомобилей"""
        try:
            # Ищем элемент с общим количеством: <span class="total"> 총<span> 10</span>대</span>
            total_element = soup.find("span", class_="total")
            if total_element:
                # Ищем вложенный span с числом
                count_span = total_element.find("span")
                if count_span:
                    count_text = count_span.get_text().strip()
                    return int(count_text)

            logger.warning("Не удалось найти общее количество автомобилей")
            return 0

        except Exception as e:
            logger.error(f"Ошибка при извлечении общего количества: {e}")
            return 0

    def _extract_cars(self, soup: BeautifulSoup) -> List[GlovisCar]:
        """Извлекает список автомобилей из HTML"""
        cars = []

        try:
            # Ищем все элементы с классом "item"
            car_items = soup.find_all("div", class_="item")

            for item in car_items:
                try:
                    car = self._parse_car_item(item)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.error(f"Ошибка при парсинге автомобиля: {e}")
                    continue

        except Exception as e:
            logger.error(f"Ошибка при извлечении списка автомобилей: {e}")

        return cars

    def _parse_car_item(self, item: Tag) -> Optional[GlovisCar]:
        """Парсит отдельный элемент автомобиля"""
        try:
            # Ищем ссылку с атрибутами
            btn_view = item.find("a", class_="btn_view")
            if not btn_view:
                return None

            # Извлекаем внутренние идентификаторы из атрибутов
            gn = btn_view.get("gn", "")
            rc = btn_view.get("rc", "")
            acc = btn_view.get("acc", "")
            atn = btn_view.get("atn", "")
            prodmancd = btn_view.get("prodmancd", "")
            reprcarcd = btn_view.get("reprcarcd", "")
            detacarcd = btn_view.get("detacarcd", "")
            cargradcd = btn_view.get("cargradcd", "")

            # Извлекаем номер выставки
            entry_info = btn_view.find("div", class_="entry-info")
            entry_number = ""
            if entry_info:
                entry_span = entry_info.find("span")
                if entry_span:
                    entry_number = entry_span.get_text().strip()

            # Извлекаем изображение
            thumbnail = btn_view.find("div", class_="thumbnail")
            main_image_url = None
            if thumbnail:
                img = thumbnail.find("img")
                if img and img.get("src"):
                    main_image_url = img.get("src")

            # Извлекаем локацию
            location_badge = btn_view.find("span", class_="tag-badge small")
            location_text = (
                location_badge.get_text().strip() if location_badge else "분당"
            )

            # Преобразуем в enum
            location = GlovisLocation.BUNDANG  # По умолчанию
            for loc in GlovisLocation:
                if loc.value == location_text:
                    location = loc
                    break

            # Извлекаем название автомобиля
            car_name_elem = btn_view.find("span", class_="car-name")
            car_name = car_name_elem.get_text().strip() if car_name_elem else ""

            # Извлекаем опции автомобиля
            option_div = btn_view.find("div", class_="option")
            options = []
            if option_div:
                spans = option_div.find_all("span")
                options = [span.get_text().strip() for span in spans]

            # Парсим опции
            year = int(options[0]) if len(options) > 0 and options[0].isdigit() else 0
            transmission = options[1] if len(options) > 1 else ""
            engine_volume = options[2] if len(options) > 2 else ""
            mileage = options[3] if len(options) > 3 else ""
            color = options[4] if len(options) > 4 else ""
            fuel_type = options[5] if len(options) > 5 else ""
            usage_type = options[6] if len(options) > 6 else ""
            condition_grade_text = options[7] if len(options) > 7 else "A/4"

            # Преобразуем оценку в enum
            condition_grade = GlovisCarCondition.A4  # По умолчанию
            for grade in GlovisCarCondition:
                if grade.value == condition_grade_text:
                    condition_grade = grade
                    break

            # Извлекаем информацию о фильтрах (номер аукциона, полоса, номер авто)
            filter_option = btn_view.find("div", class_="filter-option")
            auction_number = ""
            lane = ""
            license_plate = ""

            if filter_option:
                badges = filter_option.find_all("span", class_="tag-badge small type04")
                if len(badges) >= 3:
                    auction_number = badges[0].get_text().strip().replace("회", "")
                    lane = badges[1].get_text().strip()
                    license_plate = badges[2].get_text().strip()

            # Извлекаем стартовую цену
            price_box = btn_view.find("div", class_="price-box")
            starting_price = 0
            if price_box:
                price_num = price_box.find("span", class_="num")
                if price_num:
                    price_text = price_num.get_text().strip().replace(",", "")
                    try:
                        starting_price = int(price_text)
                    except ValueError:
                        pass

            return GlovisCar(
                entry_number=entry_number,
                car_name=car_name,
                location=location,
                lane=lane,
                license_plate=license_plate,
                year=year,
                transmission=transmission,
                engine_volume=engine_volume,
                mileage=mileage,
                color=color,
                fuel_type=fuel_type,
                usage_type=usage_type,
                condition_grade=condition_grade,
                auction_number=auction_number,
                starting_price=starting_price,
                main_image_url=main_image_url,
                gn=gn,
                rc=rc,
                acc=acc,
                atn=atn,
                prodmancd=prodmancd,
                reprcarcd=reprcarcd,
                detacarcd=detacarcd,
                cargradcd=cargradcd,
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге элемента автомобиля: {e}")
            return None

    def parse_pagination_info(self, html_content: str) -> Dict[str, Any]:
        """Извлекает информацию о пагинации"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Ищем элемент пагинации
            paging_div = soup.find("div", id="exhibit_list_paging")
            if not paging_div:
                return {"current_page": 1, "total_pages": 1}

            # Ищем кнопки пагинации
            numbers_div = paging_div.find("div", class_="numbers")
            if not numbers_div:
                return {"current_page": 1, "total_pages": 1}

            # Ищем активную страницу
            current_page = 1
            active_button = numbers_div.find("button", class_="on")
            if active_button:
                try:
                    current_page = int(active_button.get_text().strip())
                except ValueError:
                    pass

            # Подсчитываем общее количество страниц
            buttons = numbers_div.find_all("button")
            total_pages = len(buttons) if buttons else 1

            return {
                "current_page": current_page,
                "total_pages": total_pages,
            }

        except Exception as e:
            logger.error(f"Ошибка при парсинге пагинации: {e}")
            return {"current_page": 1, "total_pages": 1}
