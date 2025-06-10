import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag

from app.models.lotte import (
    LotteCar,
    LotteAuctionDate,
    FuelType,
    TransmissionType,
    GradeType,
)
from app.core.logging import logger


class LotteParser:
    """Парсер для извлечения данных с аукциона Lotte"""

    def __init__(self):
        self.logger = logger

    def parse_auction_date(self, html_content: str) -> Optional[LotteAuctionDate]:
        """
        Извлекаем дату аукциона с главной страницы Lotte

        Args:
            html_content: HTML контент главной страницы

        Returns:
            LotteAuctionDate или None если дата не найдена
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Ищем блок с датой аукциона
            auction_date_block = soup.find("p", class_="auction-date")
            if not auction_date_block:
                self.logger.warning("Не найден блок с датой аукциона")
                return None

            # Извлекаем дату из текста
            date_text = auction_date_block.get_text(strip=True)
            self.logger.info(f"Найден текст с датой: {date_text}")

            # Паттерн для извлечения даты: "경매예정일2025년 06월 16일"
            date_pattern = r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"
            match = re.search(date_pattern, date_text)

            if not match:
                self.logger.warning(f"Не удалось извлечь дату из текста: {date_text}")
                return None

            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # Формируем дату
            auction_date = f"{year:04d}-{month:02d}-{day:02d}"

            # Проверяем, является ли дата сегодняшней или будущей
            today = datetime.now().date()
            target_date = datetime(year, month, day).date()

            is_today = target_date == today
            is_future = target_date > today

            return LotteAuctionDate(
                auction_date=auction_date,
                year=year,
                month=month,
                day=day,
                is_today=is_today,
                is_future=is_future,
                raw_text=date_text,
            )

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге даты аукциона: {e}")
            return None

    def parse_cars_list(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Извлекаем список автомобилей со страницы списка Lotte

        Args:
            html_content: HTML контент страницы со списком автомобилей

        Returns:
            Список словарей с базовой информацией об автомобилях
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            cars = []

            # Ищем таблицу с автомобилями
            table = soup.find("table", class_="tbl-t02")
            if not table:
                self.logger.warning("Не найдена таблица с автомобилями")
                return cars

            tbody = table.find("tbody")
            if not tbody:
                self.logger.warning("Не найден tbody в таблице")
                return cars

            rows = tbody.find_all("tr")
            self.logger.info(f"Найдено {len(rows)} строк с автомобилями")

            for row in rows:
                try:
                    car_data = self._parse_car_row(row)
                    if car_data:
                        cars.append(car_data)
                except Exception as e:
                    self.logger.error(f"Ошибка при парсинге строки автомобиля: {e}")
                    continue

            return cars

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге списка автомобилей: {e}")
            return []

    def parse_total_count(self, html_content: str) -> int:
        """Извлекает общее количество автомобилей из HTML"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Ищем информацию о пагинации и общем количестве
            # Обычно это находится в элементах типа "1/23" или "총 234건"

            # Вариант 1: Поиск текста с "총 [число]건"
            total_pattern = re.search(r"총\s*(\d+(?:,\d+)*)\s*건", html_content)
            if total_pattern:
                total_str = total_pattern.group(1).replace(",", "")
                return int(total_str)

            # Вариант 2: Поиск в пагинации
            pagination_selectors = [
                ".pagination .total",
                ".paging .total",
                ".page-info .total",
                ".search-result .total",
                ".list-info .total",
            ]

            for selector in pagination_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    numbers = re.findall(r"\d+(?:,\d+)*", text)
                    if numbers:
                        # Берем самое большое число (скорее всего общее количество)
                        max_number = max([int(n.replace(",", "")) for n in numbers])
                        if max_number > 0:
                            return max_number

            # Вариант 3: Поиск в скриптах или hidden полях
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string:
                    # Ищем totalCount, totalRows и т.п.
                    total_matches = re.findall(
                        r'(?:totalCount|totalRows|totalRecords|total)["\']?\s*[:\=]\s*["\']?(\d+)',
                        script.string,
                        re.IGNORECASE,
                    )
                    if total_matches:
                        return int(total_matches[0])

            # Вариант 4: Считаем строки в таблице и умножаем на количество страниц
            table_rows = soup.select(
                'table tr[id*="row"], table tr.data-row, .car-list tr'
            )
            if table_rows:
                # Если есть строки, пытаемся найти информацию о страницах
                page_info = soup.find(text=re.compile(r"페이지|page", re.IGNORECASE))
                if page_info:
                    page_numbers = re.findall(r"\d+", page_info)
                    if len(page_numbers) >= 2:
                        current_page = int(page_numbers[0])
                        total_pages = int(page_numbers[1])
                        rows_per_page = len(table_rows)
                        estimated_total = total_pages * rows_per_page
                        self.logger.info(
                            f"Приблизительная оценка: {estimated_total} автомобилей"
                        )
                        return estimated_total

                # Если страниц нет, возвращаем количество строк на текущей странице
                return len(table_rows)

            self.logger.warning("Не удалось найти общее количество автомобилей")
            return 0

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге общего количества: {e}")
            return 0

    def _parse_car_row(self, row: Tag) -> Optional[Dict[str, Any]]:
        """Парсит строку таблицы с информацией об автомобиле"""
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 10:
                return None

            # Извлекаем данные из onclick атрибута ссылки
            link = row.find("a", class_="a_list")
            if not link or "onclick" not in link.attrs:
                return None

            onclick = link["onclick"]
            # Паттерн: fnPopupCarView("SA","SA202506020001","1")
            pattern = r'fnPopupCarView\("([^"]+)","([^"]+)","([^"]+)"\)'
            match = re.search(pattern, onclick)

            if not match:
                return None

            searchMngDivCd = match.group(1)
            searchMngNo = match.group(2)
            searchExhiRegiSeq = match.group(3)

            # Извлекаем данные из ячеек
            auction_number = cells[1].get_text(strip=True)  # Номер на аукционе
            lane = cells[2].get_text(strip=True)  # Полоса
            license_plate = cells[3].get_text(strip=True)  # Номер автомобиля
            name = cells[4].get_text(strip=True)  # Название автомобиля
            year_text = cells[5].get_text(strip=True)  # Год
            mileage_text = cells[6].get_text(strip=True)  # Пробег
            color = cells[7].get_text(strip=True)  # Цвет
            grade = cells[8].get_text(strip=True)  # Оценка
            price_text = cells[9].get_text(strip=True)  # Стартовая цена

            # Парсим год
            year = int(year_text) if year_text.isdigit() else 2000

            # Парсим пробег
            mileage = self._parse_mileage(mileage_text)

            # Парсим цену
            starting_price = self._parse_price(price_text)

            # Создаем уникальный ID
            car_id = f"{searchMngDivCd}_{searchMngNo}_{searchExhiRegiSeq}"

            return {
                "id": car_id,
                "auction_number": auction_number,
                "lane": lane,
                "license_plate": license_plate,
                "name": name,
                "year": year,
                "mileage": mileage,
                "color": color,
                "grade": self._normalize_grade(grade),
                "starting_price": starting_price,
                "searchMngDivCd": searchMngDivCd,
                "searchMngNo": searchMngNo,
                "searchExhiRegiSeq": searchExhiRegiSeq,
            }

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге строки: {e}")
            return None

    def parse_car_details(
        self, html_content: str, car_basic_data: Dict[str, Any]
    ) -> Optional[LotteCar]:
        """
        Парсит детальную информацию об автомобиле

        Args:
            html_content: HTML контент детальной страницы
            car_basic_data: Базовые данные об автомобиле из списка

        Returns:
            LotteCar объект с полной информацией
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Извлекаем дополнительную информацию из детальной страницы
            details = self._extract_car_details(soup)

            # Извлекаем изображения
            images = self._extract_images(soup)

            # Определяем марку и модель из названия
            brand, model = self._parse_brand_model(car_basic_data["name"])

            # Создаем объект автомобиля
            car = LotteCar(
                id=car_basic_data["id"],
                auction_number=car_basic_data["auction_number"],
                lane=car_basic_data["lane"],
                license_plate=car_basic_data["license_plate"],
                name=car_basic_data["name"],
                model=model,
                brand=brand,
                year=car_basic_data["year"],
                mileage=car_basic_data["mileage"],
                fuel_type=details.get("fuel_type", FuelType.UNKNOWN),
                transmission=details.get("transmission", TransmissionType.UNKNOWN),
                engine_capacity=details.get("engine_capacity"),
                color=car_basic_data["color"],
                grade=car_basic_data["grade"],
                starting_price=car_basic_data["starting_price"],
                first_registration_date=details.get("first_registration_date"),
                inspection_valid_until=details.get("inspection_valid_until"),
                usage_type=details.get("usage_type"),
                owner_info=details.get("owner_info"),
                vin_number=details.get("vin_number"),
                engine_model=details.get("engine_model"),
                images=images,
                searchMngDivCd=car_basic_data["searchMngDivCd"],
                searchMngNo=car_basic_data["searchMngNo"],
                searchExhiRegiSeq=car_basic_data["searchExhiRegiSeq"],
            )

            return car

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге деталей автомобиля: {e}")
            return None

    def _extract_car_details(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Извлекает детальную информацию об автомобиле из HTML"""
        details = {}

        try:
            # Ищем таблицу с детальной информацией
            detail_tables = soup.find_all("table", class_="tbl-v02")

            for table in detail_tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    if len(cells) >= 2:
                        for i in range(0, len(cells) - 1, 2):
                            header = cells[i].get_text(strip=True)
                            value = cells[i + 1].get_text(strip=True)

                            # Маппинг полей
                            if "최초등록일" in header:
                                details["first_registration_date"] = (
                                    self._normalize_date(value)
                                )
                            elif "변속기" in header:
                                details["transmission"] = self._normalize_transmission(
                                    value
                                )
                            elif "용도" in header:
                                details["usage_type"] = value
                            elif "연료" in header:
                                details["fuel_type"] = self._normalize_fuel_type(value)
                            elif "검사유효기간" in header:
                                details["inspection_valid_until"] = (
                                    self._normalize_date(value)
                                )
                            elif "차대번호" in header:
                                details["vin_number"] = value
                            elif "원동기형식" in header:
                                details["engine_model"] = value
                            elif "소유자" in header:
                                # Извлекаем информацию о владельце из следующих строк
                                owner_info = self._extract_owner_info(table)
                                if owner_info:
                                    details["owner_info"] = owner_info

        except Exception as e:
            self.logger.error(f"Ошибка при извлечении деталей: {e}")

        return details

    def _extract_owner_info(self, table: Tag) -> Optional[str]:
        """Извлекает информацию о владельце"""
        try:
            rows = table.find_all("tr")
            owner_parts = []

            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    header = cells[0].get_text(strip=True)
                    if "상호" in header or "성명" in header:
                        value = cells[1].get_text(strip=True)
                        if value and value != "******-*******":
                            owner_parts.append(value)

            return " ".join(owner_parts) if owner_parts else None

        except Exception as e:
            self.logger.error(f"Ошибка при извлечении информации о владельце: {e}")
            return None

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Извлекает URL изображений автомобиля"""
        images = []

        try:
            # Ищем все изображения автомобиля
            img_selectors = [
                'img[src*="AU_CAR_IMG"]',
                'img[src*="lotteautoauction.net"]',
                'img[id^="carImg"]',
            ]

            for selector in img_selectors:
                imgs = soup.select(selector)
                for img in imgs:
                    src = img.get("src")
                    if src and src not in images:
                        # Убеждаемся, что URL полный
                        if src.startswith("http"):
                            images.append(src)
                        elif src.startswith("/"):
                            images.append(f"https://www.lotteautoauction.net{src}")

        except Exception as e:
            self.logger.error(f"Ошибка при извлечении изображений: {e}")

        return images[:10]  # Ограничиваем количество изображений

    def _parse_mileage(self, mileage_text: str) -> int:
        """Парсит пробег из текста"""
        try:
            # Удаляем все символы кроме цифр
            numbers = re.findall(r"\d+", mileage_text.replace(",", ""))
            if numbers:
                return int("".join(numbers))
        except:
            pass
        return 0

    def _parse_price(self, price_text: str) -> int:
        """Парсит цену из текста"""
        try:
            # Извлекаем числа из текста
            numbers = re.findall(r"\d+", price_text.replace(",", ""))
            if numbers:
                price = int("".join(numbers))
                # Если цена в миллионах вонов (만원), умножаем на 10000
                if "만원" in price_text:
                    price = price * 10000
                return price
        except:
            pass
        return 0

    def _normalize_grade(self, grade: str) -> GradeType:
        """Нормализует оценку состояния"""
        grade = grade.strip().upper()
        grade_mapping = {
            "A/A": GradeType.A_A,
            "A/B": GradeType.A_B,
            "A/C": GradeType.A_C,
            "A/D": GradeType.A_D,
            "B/A": GradeType.B_A,
            "B/B": GradeType.B_B,
            "B/C": GradeType.B_C,
            "B/D": GradeType.B_D,
            "C/A": GradeType.C_A,
            "C/B": GradeType.C_B,
            "C/C": GradeType.C_C,
            "C/D": GradeType.C_D,
            "D/A": GradeType.D_A,
            "D/B": GradeType.D_B,
            "D/C": GradeType.D_C,
            "D/D": GradeType.D_D,
        }
        return grade_mapping.get(grade, GradeType.UNKNOWN)

    def _normalize_transmission(self, transmission: str) -> TransmissionType:
        """Нормализует тип коробки передач"""
        transmission = transmission.lower()
        if (
            "자동" in transmission
            or "automatic" in transmission
            or "auto" in transmission
        ):
            return TransmissionType.AUTOMATIC
        elif "수동" in transmission or "manual" in transmission:
            return TransmissionType.MANUAL
        elif "cvt" in transmission:
            return TransmissionType.CVT
        return TransmissionType.UNKNOWN

    def _normalize_fuel_type(self, fuel: str) -> FuelType:
        """Нормализует тип топлива"""
        fuel = fuel.lower()
        if "가솔린" in fuel and "하이브리드" in fuel:
            return FuelType.HYBRID
        elif "가솔린" in fuel or "gasoline" in fuel:
            return FuelType.GASOLINE
        elif "디젤" in fuel or "diesel" in fuel:
            return FuelType.DIESEL
        elif "하이브리드" in fuel or "hybrid" in fuel:
            return FuelType.HYBRID
        elif "lpg" in fuel:
            return FuelType.LPG
        elif "전기" in fuel or "electric" in fuel:
            return FuelType.ELECTRIC
        return FuelType.UNKNOWN

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Нормализует дату в формат YYYY-MM-DD"""
        try:
            # Паттерн для корейских дат: 2014.02.14 или 2026년 02월 13일
            patterns = [
                r"(\d{4})\.(\d{1,2})\.(\d{1,2})",
                r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일",
            ]

            for pattern in patterns:
                match = re.search(pattern, date_str)
                if match:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    return f"{year:04d}-{month:02d}-{day:02d}"
        except:
            pass
        return None

    def _parse_brand_model(self, name: str) -> tuple[str, str]:
        """Извлекает марку и модель из названия автомобиля"""
        try:
            # Общие корейские марки
            brands = [
                "GRANDEUR",
                "SONATA",
                "ELANTRA",
                "ACCENT",
                "TUCSON",
                "SANTA FE",
                "GENESIS",  # Hyundai
                "K5",
                "K7",
                "K8",
                "K9",
                "SPORTAGE",
                "SORENTO",
                "CARNIVAL",
                "MOHAVE",  # Kia
                "SPARK",
                "CRUZE",
                "MALIBU",
                "EQUINOX",
                "TRAVERSE",  # Chevrolet
                "QM6",
                "QM3",
                "SM6",
                "SM3",
                "XM3",  # Renault Samsung
                "KORANDO",
                "TIVOLI",
                "REXTON",
                "ACTYON",  # SsangYong
            ]

            name_upper = name.upper()

            # Ищем марку в названии
            for brand in brands:
                if brand in name_upper:
                    return brand, name

            # Если конкретная марка не найдена, попробуем определить по общим паттернам
            if "GRANDEUR" in name_upper or "GENESIS" in name_upper:
                return "HYUNDAI", name
            elif any(
                k in name_upper for k in ["K5", "K7", "K8", "K9", "SPORTAGE", "SORENTO"]
            ):
                return "KIA", name
            elif "STAREX" in name_upper:
                return "HYUNDAI", name

            return "UNKNOWN", name

        except:
            return "UNKNOWN", name
