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
    AutohubInspectionReport,
    AutohubInspectionItem,
    # Новые модели для схемы деталей
    AutohubCarDiagram,
    AutohubCarPart,
    CarPartCondition,
    CarType,
    CAR_PART_ZONES,
    CAR_TYPE_MAPPING,
    BACKGROUND_IMAGES,
    CONDITION_CODES,
    SEDAN_PARTS,
    CATEGORY_NAMES,
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

            # Извлекаем информацию об аукционе из страницы
            auction_info = self._extract_auction_info(soup)
            logger.info(f"Извлечена информация об аукционе: {auction_info}")

            # Сначала пробуем найти grid layout (новый формат)
            car_grids = soup.find_all("div", class_="car-grid")
            car_blocks = []

            if car_grids:
                # Новый формат: div-based grid layout
                logger.info(
                    f"Найден grid layout с {len(car_grids)} блоками автомобилей"
                )
                car_blocks = car_grids
            else:
                # Старый формат: table-based layout
                tbody = soup.find("tbody", class_="text-center text_vert_midd")

                if tbody:
                    # Если нашли tbody, ищем все строки в нем
                    car_blocks = tbody.find_all("tr")
                    logger.info(
                        f"Найден tbody с классом 'text-center text_vert_midd', содержит {len(car_blocks)} строк"
                    )
                else:
                    # Если не нашли tbody с классом, ищем все таблицы и берем первую подходящую
                    logger.warning(
                        "Не найден ни grid layout, ни tbody с классом, ищем альтернативные способы"
                    )
                    tables = soup.find_all("table", class_=lambda x: x and "table" in x)
                    for table in tables:
                        tbody = table.find("tbody")
                        if tbody:
                            rows = tbody.find_all("tr")
                            if rows:
                                car_blocks.extend(rows)
                                logger.info(f"Найдена таблица с {len(rows)} строками")
                                break

            logger.info(f"Найдено {len(car_blocks)} строк с автомобилями")

            for idx, block in enumerate(car_blocks):
                try:
                    car_data = self._parse_single_car(block, auction_info)
                    if car_data:
                        cars.append(car_data)
                        logger.debug(
                            f"Успешно спарсен автомобиль {idx + 1}: {car_data.title}"
                        )
                        if idx < 3:  # Логируем первые 3 автомобиля для отладки
                            logger.info(
                                f"Автомобиль {idx + 1}: {car_data.title}, год: {car_data.year}, пробег: {car_data.mileage}, топливо: {car_data.fuel_type}"
                            )
                    else:
                        logger.warning(f"Не удалось извлечь данные из блока {idx + 1}")
                except Exception as e:
                    logger.error(f"Ошибка при парсинге автомобиля {idx + 1}: {e}")
                    # Log the HTML content of failed block for debugging
                    try:
                        block_html = str(block)[:500]  # First 500 chars
                        logger.debug(
                            f"HTML блока {idx + 1} (первые 500 символов): {block_html}"
                        )
                    except:
                        pass
                    continue

            logger.info(f"Успешно спарсено {len(cars)} автомобилей")
            return cars

        except Exception as e:
            logger.error(f"Ошибка при парсинге списка автомобилей: {e}")
            return []

    def _extract_auction_info(self, soup: BeautifulSoup) -> Dict[str, Optional[str]]:
        """
        Извлекает информацию об аукционе из HTML страницы

        Args:
            soup: BeautifulSoup объект страницы

        Returns:
            Dict: Информация об аукционе
        """
        auction_info = {
            "auction_date": None,
            "auction_title": None,
            "auction_code": None,
            "receive_code": None,
        }

        try:
            # Пытаемся найти информацию об аукционе в скрытых полях формы
            hidden_inputs = soup.find_all("input", type="hidden")
            for input_field in hidden_inputs:
                name = input_field.get("name", "")
                value = input_field.get("value", "")

                if "StartDt" in name or "AucDate" in name:
                    auction_info["auction_date"] = value
                elif "AucTitle" in name or "title" in name.lower():
                    auction_info["auction_title"] = value
                elif "AucCode" in name:
                    auction_info["auction_code"] = value
                elif "receivecd" in name.lower() or "receiveCd" in name:
                    auction_info["receive_code"] = value

            # Пытаемся найти информацию в заголовке страницы
            title_element = soup.find("title")
            if title_element and not auction_info["auction_title"]:
                title_text = title_element.get_text(strip=True)
                # Извлекаем название аукциона из заголовка
                if "경매" in title_text or "auction" in title_text.lower():
                    auction_info["auction_title"] = title_text

            # Пытаемся найти информацию в элементах страницы
            auction_info_element = soup.find(
                "div", class_=lambda x: x and "auction" in x.lower()
            )
            if auction_info_element:
                text = auction_info_element.get_text(strip=True)
                # Ищем дату в формате YYYY-MM-DD или YYYY/MM/DD
                date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", text)
                if date_match and not auction_info["auction_date"]:
                    auction_info["auction_date"] = date_match.group(1).replace("/", "-")

            # Ищем информацию в JavaScript переменных
            script_tags = soup.find_all("script")
            for script in script_tags:
                if script.string:
                    script_content = script.string

                    # Ищем JavaScript переменные с информацией об аукционе
                    patterns = {
                        "auction_date": [
                            r'auc_date\s*[:=]\s*["\']([^"\']+)["\']',
                            r'startDt\s*[:=]\s*["\']([^"\']+)["\']',
                        ],
                        "auction_title": [
                            r'auc_title\s*[:=]\s*["\']([^"\']+)["\']',
                            r'aucTitle\s*[:=]\s*["\']([^"\']+)["\']',
                        ],
                        "auction_code": [
                            r'auc_code\s*[:=]\s*["\']([^"\']+)["\']',
                            r'aucCode\s*[:=]\s*["\']([^"\']+)["\']',
                        ],
                        "receive_code": [
                            r'receive_code\s*[:=]\s*["\']([^"\']+)["\']',
                            r'receivecd\s*[:=]\s*["\']([^"\']+)["\']',
                        ],
                    }

                    for key, pattern_list in patterns.items():
                        if not auction_info[key]:  # Если еще не найдено
                            for pattern in pattern_list:
                                match = re.search(
                                    pattern, script_content, re.IGNORECASE
                                )
                                if match:
                                    auction_info[key] = match.group(1)
                                    break

            # Логируем найденную информацию
            found_info = {k: v for k, v in auction_info.items() if v}
            if found_info:
                logger.info(f"Найдена информация об аукционе: {found_info}")
            else:
                logger.warning("Информация об аукционе не найдена в HTML")

        except Exception as e:
            logger.error(f"Ошибка при извлечении информации об аукционе: {e}")

        return auction_info

    def _parse_single_car(
        self, car_block: Tag, auction_info: Dict[str, Optional[str]] = None
    ) -> Optional[AutohubCar]:
        """
        Парсит информацию об одном автомобиле

        Args:
            car_block: BeautifulSoup элемент с информацией об автомобиле
            auction_info: Информация об аукционе

        Returns:
            AutohubCar: Данные об автомобиле
        """
        try:
            # Определяем формат блока (grid или table)
            is_grid_format = car_block.name == "div" and "car-grid" in car_block.get(
                "class", []
            )

            if is_grid_format:
                logger.debug("Обрабатываем блок в формате grid")
            else:
                logger.debug("Обрабатываем блок в формате table")

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

            # Используем информацию об аукционе, если она доступна
            auction_data = auction_info or {}

            # ИСПРАВЛЕНИЕ: receive_code должен равняться car_id для каждого автомобиля
            # вместо общего значения из auction_info
            individual_receive_code = car_id  # Используем car_id как receive_code

            # Создаем объект автомобиля
            car = AutohubCar(
                car_id=car_id,
                title=title,
                # Идентификаторы
                auction_number=identifiers.get("auction_number", ""),
                car_number=identifiers.get("car_number", ""),
                parking_number=identifiers.get("parking_number", ""),
                lane=identifiers.get("lane"),
                # Информация об аукционе
                auction_date=auction_data.get("auction_date"),
                auction_title=auction_data.get("auction_title"),
                auction_code=auction_data.get("auction_code"),
                receive_code=individual_receive_code,  # Используем car_id
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
            # В таблице Autohub ссылка с onclick находится в ячейке
            links = car_block.find_all("a", onclick=True)
            for link in links:
                onclick = link.get("onclick", "")
                # Ищем паттерн carInfo('RC202507230743')
                match = re.search(r"carInfo\(['\"]([^'\"]+)['\"]\)", onclick)
                if match:
                    car_id = match.group(1)
                    logger.debug(f"Найден car_id: {car_id}")
                    return car_id

            # Дополнительный поиск в JavaScript функциях
            onclick_elements = car_block.find_all(attrs={"onclick": True})
            for elem in onclick_elements:
                onclick = elem.get("onclick", "")
                match = re.search(r"carInfo\(['\"]([^'\"]+)['\"]\)", onclick)
                if match:
                    car_id = match.group(1)
                    logger.debug(f"Найден car_id (альтернативный метод): {car_id}")
                    return car_id

            logger.warning("car_id не найден в строке таблицы")
        except Exception as e:
            logger.error(f"Ошибка при извлечении car_id: {e}")
        return None

    def _extract_title(self, car_block: Tag) -> Optional[str]:
        """Извлекает название автомобиля"""
        try:
            # Сначала пробуем найти в div с классом car-title (grid format)
            car_title_div = car_block.find("div", class_="car-title")
            if car_title_div:
                title_link = car_title_div.find("a")
                if title_link:
                    text = title_link.get_text(strip=True)
                    if text:
                        logger.debug(f"Найдено название в car-title div: {text}")
                        return text

            # Если не нашли, ищем по старому способу (table format)
            links = car_block.find_all("a")
            for link in links:
                # Проверяем, есть ли onclick с carInfo
                onclick = link.get("onclick", "")
                if "carInfo" in onclick:
                    # Ищем strong внутри ссылки
                    strong = link.find("strong")
                    if strong:
                        title = strong.get_text(strip=True)
                        if title:
                            logger.debug(f"Найдено название в strong: {title}")
                            return title
                    # Если нет strong, берем текст ссылки
                    title = link.get_text(strip=True)
                    if title:
                        logger.debug(f"Найдено название в ссылке: {title}")
                        return title

            # Альтернативный поиск - первый strong тег в строке
            strong_tags = car_block.find_all("strong")
            for strong in strong_tags:
                text = strong.get_text(strip=True)
                if text and len(text) > 5:  # Минимальная длина для названия
                    logger.debug(f"Найдено название в strong (альтернативный): {text}")
                    return text

        except Exception as e:
            logger.error(f"Ошибка при извлечении title: {e}")
        return None

    def _extract_car_info(self, car_block: Tag) -> Dict[str, Any]:
        """Извлекает основную информацию об автомобиле из ячеек таблицы"""
        info = {}

        try:
            # Сначала пробуем grid format
            car_list_div = car_block.find("div", class_="car-list")
            if car_list_div:
                # Grid format - ищем ul с информацией
                info_list = car_list_div.find("ul", class_="list-inline")
                if info_list:
                    list_items = info_list.find_all("li")
                    logger.debug(f"Найден список с {len(list_items)} элементами")

                    for item in list_items:
                        text = item.get_text(strip=True)

                        # Год (4 цифры)
                        if re.match(r"^\d{4}$", text):
                            info["year"] = int(text)
                            logger.debug(f"Найден год: {info['year']}")

                        # Пробег (содержит km)
                        elif "km" in text.lower():
                            info["mileage"] = text
                            logger.debug(f"Найден пробег: {info['mileage']}")

                        # Трансмиссия
                        elif text in [
                            "오토",
                            "수동",
                            "자동",
                            "CVT",
                            "DCT",
                            "Auto",
                            "Manual",
                        ]:
                            info["transmission"] = self._parse_transmission(text)
                            logger.debug(
                                f"Найдена трансмиссия: {text} -> {info['transmission']}"
                            )

                        # Тип топлива
                        elif text in [
                            "휘발유",
                            "경유",
                            "전기",
                            "하이브리드",
                            "LPG",
                            "디젤",
                            "가솔린",
                            "CNG",
                            "수소",
                        ]:
                            info["fuel_type"] = self._parse_fuel_type(text)
                            logger.debug(
                                f"Найден тип топлива: {text} -> {info['fuel_type']}"
                            )

                        # Цвет
                        elif text in [
                            "흰색",
                            "검정색",
                            "회색",
                            "파란색",
                            "빨간색",
                            "은색",
                            "기타",
                        ]:
                            info["color"] = text
                            logger.debug(f"Найден цвет: {info['color']}")

                    return info

            # Table format - старый способ
            cells = car_block.find_all("td")

            if len(cells) >= 5:  # Ожидаем минимум 5 ячеек
                # Обычная структура:
                # 0 - чекбокс
                # 1 - название и основная инфо
                # 2 - год/пробег/трансмиссия/топливо
                # 3 - номера (аукцион/парковка)
                # 4 - цена
                # 5 - статус (если есть)

                # Извлекаем из второй ячейки (основная информация)
                if len(cells) > 2:
                    info_cell = cells[2]
                    info_text = info_cell.get_text(
                        " ", strip=True
                    )  # Используем пробел как разделитель
                    logger.debug(f"Извлечен текст из info_cell: {info_text}")

                    # Парсим год, пробег, трансмиссию и топливо
                    # Формат: "2020 33,076km 오토 경유"
                    parts = info_text.split()

                    if len(parts) >= 1:
                        # Год
                        for part in parts:
                            year_match = re.search(r"^(\d{4})$", part)
                            if year_match:
                                info["year"] = int(year_match.group(1))
                                logger.debug(f"Найден год: {info['year']}")
                                break

                        # Пробег
                        for part in parts:
                            if "km" in part.lower():
                                info["mileage"] = part
                                logger.debug(f"Найден пробег: {info['mileage']}")
                                break

                        # Трансмиссия
                        for part in parts:
                            if part in ["오토", "수동", "자동", "CVT", "DCT"]:
                                info["transmission"] = self._parse_transmission(part)
                                logger.debug(
                                    f"Найдена трансмиссия: {part} -> {info['transmission']}"
                                )
                                break

                        # Тип топлива
                        for part in parts:
                            if part in [
                                "휘발유",
                                "경유",
                                "전기",
                                "하이브리드",
                                "LPG",
                                "디젤",
                                "가솔린",
                            ]:
                                info["fuel_type"] = self._parse_fuel_type(part)
                                logger.debug(
                                    f"Найден тип топлива: {part} -> {info['fuel_type']}"
                                )
                                break

                    # Проверяем на дату регистрации в тексте
                    reg_match = re.search(r"최초등록일\s*:\s*(\d{8})", info_text)
                    if reg_match:
                        raw_date = reg_match.group(1)
                        formatted_date = (
                            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                        )
                        info["first_registration_date"] = formatted_date
                        logger.debug(
                            f"📅 Найдена дата регистрации: {raw_date} -> {formatted_date}"
                        )

                # Альтернативный поиск в br разделенном тексте
                br_texts = []
                for cell in cells:
                    # Извлекаем текст между br тегами
                    for br in cell.find_all("br"):
                        if br.previous_sibling:
                            text = str(br.previous_sibling).strip()
                            if text:
                                br_texts.append(text)
                        if br.next_sibling:
                            text = str(br.next_sibling).strip()
                            if text:
                                br_texts.append(text)

                # Парсим дополнительную информацию из br текстов
                for text in br_texts:
                    # Год с датой регистрации
                    year_reg_match = re.search(
                        r"(\d{4})\s*\(최초등록일\s*:\s*(\d{8})\)", text
                    )
                    if year_reg_match:
                        info["year"] = int(year_reg_match.group(1))
                        raw_date = year_reg_match.group(2)
                        info["first_registration_date"] = (
                            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                        )

                    # Отдельная дата регистрации
                    elif "최초등록일" in text:
                        reg_match = re.search(r"최초등록일\s*:\s*(\d{8})", text)
                        if reg_match:
                            raw_date = reg_match.group(1)
                            info["first_registration_date"] = (
                                f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                            )

                    # Оценка состояния
                    elif "평가점" in text:
                        grade_match = re.search(r"평가점\s*:\s*([^\s]+)", text)
                        if grade_match:
                            info["condition_grade"] = grade_match.group(1)

                    # История
                    elif "경력" in text:
                        history_match = re.search(r"경력\s*:\s*(.+)", text)
                        if history_match:
                            info["history"] = history_match.group(1).strip()

        except Exception as e:
            logger.error(f"Ошибка при извлечении car_info: {e}")

        return info

    def _extract_identifiers(self, car_block: Tag) -> Dict[str, str]:
        """Извлекает идентификаторы автомобиля из ячеек таблицы"""
        identifiers = {}

        try:
            # Сначала пробуем grid format
            # В grid format номер аукциона часто в кнопках
            buttons = car_block.find_all("button")
            for button in buttons:
                onclick = button.get("onclick", "")
                # Ищем кнопки с onclick функциями
                if "regInterest" in onclick:
                    # regInterest('1001','N','RC202507230743')
                    match = re.search(r"regInterest\(['\"]([^'\"]+)['\"].*\)", onclick)
                    if match:
                        identifiers["auction_number"] = match.group(1)
                        logger.debug(
                            f"Найден номер аукциона в onclick: {identifiers['auction_number']}"
                        )
                        break

            # Table format
            cells = car_block.find_all("td")

            # Обычно номера находятся в 3-4 ячейке
            if len(cells) > 3:
                numbers_cell = cells[3]
                numbers_text = numbers_cell.get_text(strip=True)

                # Парсим номера из текста вида "0289 / D-1342"
                if "/" in numbers_text:
                    parts = numbers_text.split("/")
                    if len(parts) >= 2:
                        identifiers["auction_number"] = parts[0].strip()
                        identifiers["parking_number"] = parts[1].strip()

                        # Извлекаем полосу из парковочного номера (например, "D" из "D-1342")
                        parking = parts[1].strip()
                        if "-" in parking:
                            lane = parking.split("-")[0]
                            identifiers["lane"] = lane

            # Альтернативный поиск в font тегах с цветом
            font_tags = car_block.find_all("font")
            for font in font_tags:
                color = font.get("color", "")
                text = font.get_text(strip=True)

                # Красный цвет часто используется для номера аукциона
                if color.lower() in ["red", "#ff0000", "#f00"] and text.isdigit():
                    if "auction_number" not in identifiers:
                        identifiers["auction_number"] = text

                # Синий цвет часто для парковочного номера
                elif color.lower() in ["blue", "#0000ff", "#00f"] and "-" in text:
                    if "parking_number" not in identifiers:
                        identifiers["parking_number"] = text
                        # Извлекаем полосу
                        if "-" in text:
                            lane = text.split("-")[0]
                            identifiers["lane"] = lane

            # Поиск номера автомобиля в тексте
            all_text = car_block.get_text()
            car_num_match = re.search(r"차량번호\s*:\s*([^\s]+)", all_text)
            if car_num_match:
                identifiers["car_number"] = car_num_match.group(1)

        except Exception as e:
            logger.error(f"Ошибка при извлечении identifiers: {e}")

        return identifiers

    def _extract_financial_info(self, car_block: Tag) -> Dict[str, Optional[int]]:
        """Извлекает финансовую информацию из ячеек таблицы"""
        financial = {}

        try:
            # Ищем цену по структуре HTML с лейблом "시작가"
            # Структура: <strong class="car_list_item">시작가 : </strong><strong class="i_comm_main_txt2">3,270</strong>
            
            # Сначала ищем все strong элементы с классом car_list_item
            labels = car_block.find_all("strong", class_="car_list_item")
            for label in labels:
                label_text = label.get_text(strip=True)
                if "시작가" in label_text:  # "Starting price" in Korean
                    # Ищем следующий sibling strong с классом i_comm_main_txt2
                    next_sibling = label.find_next_sibling("strong", class_="i_comm_main_txt2")
                    if next_sibling:
                        price_text = next_sibling.get_text(strip=True)
                        # Убираем запятые и преобразуем в число
                        price_clean = price_text.replace(",", "")
                        if price_clean.isdigit():
                            financial["starting_price"] = int(price_clean)
                            logger.debug(f"Найдена цена по лейблу '시작가': {financial['starting_price']} 만원")
                            break
            
            # Альтернативный поиск - ищем все strong с классом i_comm_main_txt2
            if "starting_price" not in financial:
                price_elements = car_block.find_all("strong", class_="i_comm_main_txt2")
                for elem in price_elements:
                    # Проверяем, что перед этим элементом есть текст "시작가"
                    parent = elem.parent
                    if parent:
                        parent_text = parent.get_text(strip=True)
                        if "시작가" in parent_text:
                            price_text = elem.get_text(strip=True)
                            price_clean = price_text.replace(",", "")
                            if price_clean.isdigit():
                                financial["starting_price"] = int(price_clean)
                                logger.debug(f"Найдена цена в i_comm_main_txt2: {financial['starting_price']} 만원")
                                break
            
            # Grid format - ищем в кнопках или тексте (оставляем как fallback)
            if "starting_price" not in financial:
                buttons = car_block.find_all("button")
                for button in buttons:
                    onclick = button.get("onclick", "")
                    # receive_rc_autoTender_pop('RC202507230743','N','3710','1001')
                    if "receive_rc_autoTender_pop" in onclick:
                        match = re.search(
                            r"receive_rc_autoTender_pop\([^,]+,[^,]+,['\"]([^'\"]+)['\"].*\)",
                            onclick,
                        )
                        if match:
                            price_str = match.group(1)
                            if price_str.isdigit() and int(price_str) > 1000:  # Исключаем явно неправильные значения
                                financial["starting_price"] = int(price_str)
                                logger.debug(
                                    f"Найдена цена в onclick: {financial['starting_price']} 만원"
                                )
                                break

            # Table format (оставляем как последний fallback)
            if "starting_price" not in financial:
                cells = car_block.find_all("td")
                
                # Цена обычно в 3-й ячейке (после названия и оценки)
                if len(cells) > 2:
                    # Ищем ячейку с ценой по классу
                    for idx, cell in enumerate(cells):
                        cell_text = cell.get_text(strip=True)
                        
                        # Проверяем содержит ли текст признаки цены
                        if "만원" in cell_text or re.search(
                            r"\d{3,}", cell_text.replace(",", "")
                        ):
                            # Парсим цену
                            price_match = re.search(r"([\d,]+)\s*만원", cell_text)
                            if price_match:
                                price_str = price_match.group(1).replace(",", "")
                                if int(price_str) > 1000:  # Исключаем явно неправильные значения
                                    financial["starting_price"] = int(price_str)
                                    logger.debug(
                                        f"Найдена стартовая цена: {financial['starting_price']} 만원"
                                    )
                                    break

        except Exception as e:
            logger.error(f"Ошибка при извлечении financial_info: {e}")

        return financial

    def _extract_status_info(self, car_block: Tag) -> Dict[str, Any]:
        """Извлекает информацию о статусе из ячеек таблицы"""
        status_info = {}

        try:
            cells = car_block.find_all("td")

            # Статус обычно в предпоследней или последней ячейке
            if len(cells) >= 5:
                # Проверяем последние две ячейки
                for cell_idx in [-2, -1]:
                    if len(cells) > abs(cell_idx):
                        status_cell = cells[cell_idx]
                        status_text = status_cell.get_text(strip=True)

                        # Проверяем на статусы
                        if any(
                            status in status_text
                            for status in [
                                "출품등록",
                                "진행중",
                                "완료",
                                "대기",
                                "낙찰",
                                "유찰",
                            ]
                        ):
                            if "출품등록" in status_text:
                                status_info["status"] = CarStatus.REGISTERED
                            else:
                                status_info["status"] = self._parse_status(status_text)

                            # Если есть результат аукциона
                            if "낙찰" in status_text or "유찰" in status_text:
                                status_info["auction_result"] = status_text

                            logger.debug(
                                f"Найден статус: {status_text} -> {status_info['status']}"
                            )
                            break

            # По умолчанию статус REGISTERED
            if "status" not in status_info:
                status_info["status"] = CarStatus.REGISTERED
                logger.debug("Используется статус по умолчанию: REGISTERED")

        except Exception as e:
            logger.error(f"Ошибка при извлечении status_info: {e}")

        return status_info

    def _extract_main_image(self, car_block: Tag) -> Optional[str]:
        """Извлекает URL основного изображения и удаляет суффикс _M для получения полноразмерного изображения"""
        
        def process_image_url(url: str) -> str:
            """Удаляет суффикс _M из URL изображения для получения полноразмерной версии"""
            import re
            # Паттерн для поиска _M перед расширением файла
            # Например: AT175219858847000_M.jpg -> AT175219858847000.jpg
            processed_url = re.sub(r'_M(\.\w+)$', r'\1', url)
            if processed_url != url:
                logger.debug(f"Удален суффикс _M из URL: {url} -> {processed_url}")
            return processed_url
        
        try:
            # Для новой структуры HTML ищем изображение во вложенных div-ах
            # Ищем div с классом car_img_area или car-image
            img_divs = car_block.find_all(
                "div", class_=lambda x: x and ("car_img" in x or "car-image" in x)
            )

            for div in img_divs:
                img = div.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    # Если URL относительный, делаем его абсолютным
                    if src.startswith("/"):
                        full_url = f"{self.base_url}{src}"
                    elif not src.startswith("http"):
                        full_url = f"{self.base_url}/{src}"
                    else:
                        full_url = src
                    
                    # Удаляем суффикс _M для получения полноразмерного изображения
                    full_url = process_image_url(full_url)
                    logger.debug(f"Найдено изображение: {full_url}")
                    return full_url

            # Альтернативный поиск - любое изображение в строке
            img_element = car_block.find("img")
            if img_element and img_element.get("src"):
                src = img_element["src"]
                if src.startswith("/"):
                    full_url = f"{self.base_url}{src}"
                elif not src.startswith("http"):
                    full_url = f"{self.base_url}/{src}"
                else:
                    full_url = src
                
                # Удаляем суффикс _M для получения полноразмерного изображения
                full_url = process_image_url(full_url)
                logger.debug(f"Найдено изображение (альтернативный): {full_url}")
                return full_url

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

        # Парсинг технического листа с заменами и покрасками
        inspection_report = parse_inspection_report(soup)

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
            inspection_report=inspection_report,
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
                    # Поддерживаем форматы:
                    # - "2022 (최초등록일 : 20210809)"
                    # - "2021 (최초등록일 : 20210615)"
                    # - "2022" (только год)

                    year_match = re.search(r"(\d{4})", value)
                    # Новый регекс для парсинга даты регистрации в скобках
                    reg_match = re.search(r"최초등록일\s*:\s*(\d{8})", value)

                    car_info["year"] = year_match.group(1) if year_match else value
                    if reg_match:
                        # Форматируем дату из YYYYMMDD в YYYY-MM-DD
                        raw_date = reg_match.group(1)
                        formatted_date = (
                            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                        )
                        car_info["first_registration"] = formatted_date
                        car_info["first_registration_date"] = formatted_date
                        logger.debug(
                            f"📅 Найдена дата регистрации: {raw_date} -> {formatted_date}"
                        )
                    else:
                        logger.debug(
                            f"⚠️ Дата регистрации не найдена в значении: {value}"
                        )
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
        # Инициализируем пустые списки для каждой категории опций
        exterior_options = []
        interior_options = []
        safety_options = []
        convenience_options = []
        multimedia_options = []

        # Поиск блоков с опциями
        option_blocks = soup.find_all("div", class_="option-block")

        for block in option_blocks:
            category_element = block.find("h4")
            if not category_element:
                continue

            category = category_element.get_text(strip=True).lower()
            options_list = block.find_all("li")

            current_options = []
            for option in options_list:
                option_text = option.get_text(strip=True)
                if option_text:
                    current_options.append(option_text)

            # Распределяем опции по категориям
            if "외관" in category or "exterior" in category:
                exterior_options.extend(current_options)
            elif "내장" in category or "interior" in category:
                interior_options.extend(current_options)
            elif "안전" in category or "safety" in category:
                safety_options.extend(current_options)
            elif "편의" in category or "convenience" in category:
                convenience_options.extend(current_options)
            elif "멀티미디어" in category or "multimedia" in category:
                multimedia_options.extend(current_options)
            else:
                # Если категория не определена, добавляем в удобство
                convenience_options.extend(current_options)

        return AutohubOptionInfo(
            exterior_options=exterior_options,
            interior_options=interior_options,
            safety_options=safety_options,
            convenience_options=convenience_options,
            multimedia_options=multimedia_options,
        )

    except Exception as e:
        logger.error(f"Ошибка при парсинге опций: {e}")
        return AutohubOptionInfo()


def parse_images(soup: BeautifulSoup) -> List[AutohubImage]:
    """Парсинг изображений автомобиля"""
    images = []

    try:
        # Поиск больших изображений
        large_images = soup.find_all("img", class_="carImg")

        for i, img in enumerate(large_images):
            src_url = img.get("src", "")
            if src_url:
                # Убираем _L из URL чтобы получить полноразмерное изображение
                # Например: AT1753859546284n4_L.jpg -> AT1753859546284n4.jpg
                large_url = src_url.replace("_L.jpg", ".jpg")
                
                # Получение URL маленького изображения
                small_url = src_url.replace("_L.jpg", "_S.jpg")

                images.append(
                    AutohubImage(large_url=large_url, small_url=small_url, sequence=i)
                )

    except Exception as e:
        logger.error(f"Ошибка при парсинге изображений: {e}")

    return images


def parse_inspection_report(soup: BeautifulSoup) -> Optional[AutohubInspectionReport]:
    """Парсинг технического листа с заменами и покрасками"""
    try:
        # Поиск скрытых полей с данными о проверке
        inspresult_input = soup.find("input", {"id": "inspresult"})
        categorycode_input = soup.find("input", {"id": "categorycode"})

        if not inspresult_input or not categorycode_input:
            logger.warning("Не найдены данные технического листа")
            return None

        inspresult = inspresult_input.get("value", "")
        category_code = categorycode_input.get("value", "")

        if not inspresult or not category_code:
            logger.warning("Пустые данные технического листа")
            return None

        logger.info(f"🔧 Парсинг технического листа: категория {category_code}")

        # Разбираем строку результатов проверки
        inspection_data = inspresult.split(",")

        # Определяем названия частей в зависимости от категории
        if category_code == "001":
            parts_map = SEDAN_PARTS
        else:
            # Для других категорий используем базовые названия
            parts_map = {i: f"Часть {i+1}" for i in range(len(inspection_data))}

        category_name = CATEGORY_NAMES.get(category_code, f"Категория {category_code}")

        # Парсим каждую часть
        inspection_items = []
        total_items = 0
        damaged_items = 0
        replacement_needed = 0
        bodywork_needed = 0
        painting_needed = 0
        damage_summary = {}

        for i, condition_code in enumerate(inspection_data):
            if condition_code and condition_code != "@@@":
                total_items += 1

                # Получаем название части
                part_name = parts_map.get(i, f"Часть {i+1}")

                # Определяем описание состояния
                condition_desc = CONDITION_CODES.get(
                    condition_code, "Неизвестное состояние"
                )

                # Извлекаем дополнительную информацию (степень повреждения)
                severity = None
                if len(condition_code) > 3:
                    severity = condition_code[3:]

                # Создаем элемент проверки
                item = AutohubInspectionItem(
                    part_id=i,
                    part_name=part_name,
                    condition_code=condition_code,
                    condition_description=condition_desc,
                    severity=severity,
                )

                inspection_items.append(item)

                # Подсчитываем статистику
                if condition_code != "@@@":
                    damaged_items += 1

                if item.needs_replacement or item.needs_replacement_required:
                    replacement_needed += 1

                if item.needs_bodywork:
                    bodywork_needed += 1

                if item.needs_painting:
                    painting_needed += 1

                # Добавляем в сводку по типам повреждений
                base_code = (
                    condition_code[:3] if len(condition_code) >= 3 else condition_code
                )
                damage_summary[base_code] = damage_summary.get(base_code, 0) + 1

        # Ищем дополнительные комментарии
        special_notes = None
        inspector_comments = None

        # Поиск особых замечаний
        special_notes_elem = soup.find("th", string="특기사항/점검자 의견")
        if special_notes_elem:
            notes_td = special_notes_elem.find_next("td")
            if notes_td:
                special_notes = notes_td.get_text(strip=True)

        # Поиск комментариев по функциональной оценке
        func_eval_elem = soup.find("th", string="기능평가정보 상세")
        if func_eval_elem:
            comments_td = func_eval_elem.find_next("td")
            if comments_td:
                inspector_comments = comments_td.get_text(strip=True)

        # Создаем отчет
        inspection_report = AutohubInspectionReport(
            category_code=category_code,
            category_name=category_name,
            total_items=total_items,
            damaged_items=damaged_items,
            replacement_needed=replacement_needed,
            bodywork_needed=bodywork_needed,
            painting_needed=painting_needed,
            inspection_items=inspection_items,
            special_notes=special_notes,
            inspector_comments=inspector_comments,
            damage_summary=damage_summary,
        )

        logger.info(
            f"✅ Технический лист: {damaged_items}/{total_items} поврежденных частей"
        )
        logger.info(
            f"   - Замена: {replacement_needed}, Кузовной ремонт: {bodywork_needed}, Покраска: {painting_needed}"
        )

        return inspection_report

    except Exception as e:
        logger.error(f"Ошибка при парсинге технического листа: {e}")
        return None


def parse_car_diagram(soup: BeautifulSoup) -> Optional[AutohubCarDiagram]:
    """
    Парсинг схемы деталей автомобиля с информацией о повреждениях

    Args:
        soup: BeautifulSoup объект страницы автомобиля

    Returns:
        AutohubCarDiagram: Схема деталей автомобиля или None
    """
    try:
        logger.info("Начинаем парсинг схемы деталей автомобиля")

        # 1. Извлекаем скрытое поле с данными инспекции
        inspresult_input = soup.find("input", {"id": "inspresult"})
        if not inspresult_input:
            logger.warning("Не найдено поле inspresult со схемой деталей")
            return None

        inspection_data = inspresult_input.get("value", "")
        if not inspection_data:
            logger.warning("Поле inspresult пустое")
            return None

        logger.info(f"Найдены данные инспекции: {inspection_data[:100]}...")

        # 2. Определяем тип автомобиля из видимой схемы
        car_type = _determine_car_type(soup)
        background_image = BACKGROUND_IMAGES[car_type]

        logger.info(f"Определен тип автомобиля: {car_type.value}")

        # 3. Парсим коды состояний частей
        condition_codes = inspection_data.split(",")
        logger.info(f"Найдено {len(condition_codes)} кодов состояний частей")

        # 4. Извлекаем позиции частей из HTML схемы
        part_positions = _extract_part_positions(soup, car_type)
        logger.info(f"Извлечено {len(part_positions)} позиций частей")

        # 5. Создаем объекты частей автомобиля
        parts = []
        part_letter_map = _get_part_letter_map(car_type)

        for i, condition_code in enumerate(condition_codes):
            condition_code = condition_code.strip()
            if not condition_code:
                continue

            try:
                # Определяем part_id на основе индекса и типа автомобиля
                part_info = _get_part_info_by_index(i, car_type, part_letter_map)
                if not part_info:
                    continue

                # Получаем позицию части из HTML
                position = part_positions.get(part_info["part_code"], {})

                # Создаем объект части автомобиля
                car_part = AutohubCarPart(
                    part_id=part_info["part_id"],
                    part_code=part_info["part_code"],
                    condition=_parse_condition_code(condition_code),
                    condition_symbol=_extract_condition_symbol(condition_code),
                    zone=part_info["zone"],
                    position_x=position.get("x"),
                    position_y=position.get("y"),
                    image_path=part_info["image_path"],
                )

                parts.append(car_part)

            except Exception as e:
                logger.error(f"Ошибка при создании части {i}: {e}")
                continue

        # 6. Создаем схему деталей
        diagram = AutohubCarDiagram(
            car_type=car_type, background_image=background_image, parts=parts
        )

        # 7. Вычисляем статистику
        diagram.calculate_statistics()

        logger.info(
            f"Схема деталей создана: {diagram.total_parts} частей, "
            f"{diagram.damaged_parts} повреждено, "
            f"{diagram.replacement_needed} требует замены, "
            f"{diagram.repair_needed} требует ремонта"
        )

        return diagram

    except Exception as e:
        logger.error(f"Ошибка при парсинге схемы деталей: {e}")
        return None


def _determine_car_type(soup: BeautifulSoup) -> CarType:
    """Определяет тип автомобиля из видимой схемы"""

    # Проверяем какая схема активна
    car_divs = soup.find_all("div", class_=re.compile(r"car_\d+"))

    for car_div in car_divs:
        style = car_div.get("style", "")
        if "display:none" not in style:
            # Активная схема найдена
            class_name = car_div.get("class", [])
            for cls in class_name:
                if cls.startswith("car_"):
                    car_number = cls.replace("car_", "")
                    if car_number == "01":
                        return CarType.SEDAN
                    elif car_number == "02":
                        return CarType.PICKUP
                    elif car_number == "03":
                        return CarType.TRUCK

    # По умолчанию седан
    return CarType.SEDAN


def _extract_part_positions(
    soup: BeautifulSoup, car_type: CarType
) -> Dict[str, Dict[str, int]]:
    """Извлекает координаты частей из HTML схемы"""

    positions = {}

    try:
        # Ищем все элементы <li> с ID частей
        part_elements = soup.find_all("li", id=re.compile(r"[a-z]x\d+"))

        for element in part_elements:
            part_code = element.get("id", "")
            if not part_code:
                continue

            # Извлекаем позицию из style атрибута в <p> элементе
            p_element = element.find("p")
            if p_element:
                style = p_element.get("style", "")
                x_match = re.search(r"left:(\d+)px", style)
                y_match = re.search(r"top:(\d+)px", style)

                if x_match and y_match:
                    positions[part_code] = {
                        "x": int(x_match.group(1)),
                        "y": int(y_match.group(1)),
                    }

    except Exception as e:
        logger.error(f"Ошибка при извлечении позиций частей: {e}")

    return positions


def _get_part_letter_map(car_type: CarType) -> List[str]:
    """Возвращает карту букв частей для типа автомобиля"""

    if car_type == CarType.SEDAN:
        # Седан: A(01-09), B(10-22), C(25-33), D(36-50)
        return (
            ["A"] * 9  # A01-A09 (позиции 0-8)
            + ["B"] * 13  # B01-B13 (позиции 9-21)
            + ["C"] * 9  # C01-C09 (позиции 22-30)
            + ["D"] * 15  # D01-D15 (позиции 31-45)
        )
    elif car_type == CarType.PICKUP:
        # Пикап: E(01-09), F(10-23), G(25-33), H(36-50)
        return (
            ["E"] * 9  # E01-E09
            + ["F"] * 14  # F01-F14
            + ["G"] * 9  # G01-G09
            + ["H"] * 15  # H01-H15
        )
    elif car_type == CarType.TRUCK:
        # Грузовик: M(01-10), N(11-24), O(25-35), P(36-40)
        return (
            ["M"] * 10  # M01-M10
            + ["N"] * 14  # N01-N14
            + ["O"] * 11  # O01-O11
            + ["P"] * 5  # P01-P05
        )

    return []


def _get_part_info_by_index(
    index: int, car_type: CarType, part_letter_map: List[str]
) -> Optional[Dict[str, str]]:
    """Получает информацию о части по индексу"""

    if index >= len(part_letter_map):
        return None

    letter = part_letter_map[index]
    zone = CAR_PART_ZONES.get(letter, "unknown")

    # Вычисляем номер части в группе
    letter_indices = [i for i, l in enumerate(part_letter_map) if l == letter]
    part_number = letter_indices.index(index) + 1

    # Формируем идентификаторы
    part_id = f"{letter}{part_number:02d}"

    # Формируем код для HTML (например: ax010, bx015)
    if car_type == CarType.SEDAN:
        prefix = "ax"
    elif car_type == CarType.PICKUP:
        prefix = "bx"
    else:  # TRUCK
        prefix = "dx"

    # Корректируем номер для HTML ID
    html_number = _get_html_number_for_part(letter, part_number)
    part_code = f"{prefix}{html_number}"

    # Путь к изображению части
    image_path = f"/images/front/car_info/{part_id}X.png"

    return {
        "part_id": part_id,
        "part_code": part_code,
        "zone": zone,
        "image_path": image_path,
    }


def _get_html_number_for_part(letter: str, part_number: int) -> str:
    """Преобразует номер части в HTML номер"""

    # Базовая логика: для большинства частей HTML номер = номер части
    # Но есть исключения для некоторых частей

    if letter in ["A", "E", "M"]:  # Левая сторона
        if part_number <= 9:
            return f"0{part_number}0" if part_number <= 8 else f"01{part_number - 8}"
        return f"0{part_number}"
    elif letter in ["B", "F", "N"]:  # Верх
        base = 111
        return f"0{base + part_number - 1}"
    elif letter in ["C", "G", "O"]:  # Правая сторона
        base = 125
        return f"0{base + part_number - 1}"
    elif letter in ["D", "H", "P"]:  # Низ
        base = 136
        return f"0{base + part_number - 1}"

    return f"0{part_number}0"


def _parse_condition_code(code: str) -> CarPartCondition:
    """Парсит код состояния части"""

    code = code.strip()

    if code == "X@@":
        return CarPartCondition.REPLACEMENT_NEEDED
    elif code == "@A@" or code == "A@@":
        return CarPartCondition.ACCIDENT_DAMAGE
    elif code == "@U@" or code == "U@@":
        return CarPartCondition.REPAIR_NEEDED
    elif code == "@E@" or code == "E@@":
        return CarPartCondition.OPERATIONAL_DAMAGE
    elif code == "@W@" or code == "W@@":
        return CarPartCondition.WELDING_NEEDED
    else:
        return CarPartCondition.NORMAL


def _extract_condition_symbol(code: str) -> str:
    """Извлекает символ состояния из кода"""

    code = code.strip()

    if "X" in code:
        return "X"
    elif "A" in code:
        return "A"
    elif "U" in code:
        return "U"
    elif "E" in code:
        return "E"
    elif "W" in code:
        return "W"
    else:
        return ""
