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
    LotteCarDetail,
    LotteCarBasicInfo,
    LotteCarOwner,
    LotteCarTechnicalSpecs,
    LotteCarConditionCheck,
    LotteCarLegalStatus,
    LotteCarMedia,
    LotteCarInspectionRecord,
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

            # Вариант 0: Поиск специфичного для Lotte элемента .total-carnum
            total_carnum = soup.select_one(".total-carnum")
            if total_carnum:
                text = total_carnum.get_text(strip=True)
                self.logger.info(f"Найден элемент .total-carnum: '{text}'")
                # Ищем число в тексте типа "총 등록대수1,320"
                numbers = re.findall(r"\d+(?:,\d+)*", text)
                if numbers:
                    # Берем самое большое число
                    max_number = max([int(n.replace(",", "")) for n in numbers])
                    self.logger.info(f"Извлечено общее количество: {max_number}")
                    return max_number

            # Вариант 1: Поиск текста с "총 등록대수" или "총 [число]건"
            total_patterns = [
                r"총\s*등록대수\s*(\d+(?:,\d+)*)",
                r"총\s*(\d+(?:,\d+)*)\s*건",
                r"총\s*(\d+(?:,\d+)*)\s*대",
            ]

            for pattern in total_patterns:
                total_match = re.search(pattern, html_content)
                if total_match:
                    total_str = total_match.group(1).replace(",", "")
                    self.logger.info(f"Найдено по паттерну '{pattern}': {total_str}")
                    return int(total_str)

            # Вариант 2: Поиск в пагинации
            pagination_selectors = [
                ".pagination .total",
                ".paging .total",
                ".page-info .total",
                ".search-result .total",
                ".list-info .total",
                ".total-carnum",
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
                            self.logger.info(
                                f"Найдено в селекторе '{selector}': {max_number}"
                            )
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


class LotteCarDetailParser:
    """Парсер для детальной страницы автомобиля Lotte"""

    def __init__(self):
        self.soup = None

    def parse(
        self, html_content: str, source_url: Optional[str] = None
    ) -> LotteCarDetail:
        """
        Парсит HTML детальной страницы автомобиля

        Args:
            html_content: HTML контент страницы
            source_url: URL источника

        Returns:
            LotteCarDetail: Полная информация об автомобиле
        """
        try:
            self.soup = BeautifulSoup(html_content, "html.parser")

            # Парсим все компоненты
            basic_info = self._parse_basic_info()
            owner_info = self._parse_owner_info()
            technical_specs = self._parse_technical_specs()
            condition_check = self._parse_condition_check()
            legal_status = self._parse_legal_status()
            media = self._parse_media()
            inspection_record = self._parse_inspection_record()

            # Извлекаем мета-информацию
            management_data = self._parse_management_data()

            return LotteCarDetail(
                basic_info=basic_info,
                owner_info=owner_info,
                technical_specs=technical_specs,
                condition_check=condition_check,
                legal_status=legal_status,
                media=media,
                inspection_record=inspection_record,
                management_number=management_data.get("management_number"),
                management_division=management_data.get("management_division"),
                exhibition_sequence=management_data.get("exhibition_sequence"),
                parsed_at=datetime.now(),
                source_url=source_url,
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга Lotte car detail: {e}")
            # Возвращаем пустую структуру при ошибке
            return LotteCarDetail(
                basic_info=LotteCarBasicInfo(),
                owner_info=LotteCarOwner(),
                technical_specs=LotteCarTechnicalSpecs(),
                condition_check=LotteCarConditionCheck(),
                legal_status=LotteCarLegalStatus(),
                media=LotteCarMedia(),
                inspection_record=LotteCarInspectionRecord(),
                parsed_at=datetime.now(),
                source_url=source_url,
            )

    def _parse_basic_info(self) -> LotteCarBasicInfo:
        """Парсит основную информацию об автомобиле"""
        basic_info = LotteCarBasicInfo()

        try:
            # Название автомобиля
            title_elem = self.soup.find("div", class_="vehicle-tit")
            if title_elem:
                title_h2 = title_elem.find("h2", class_="tit")
                if title_h2:
                    basic_info.title = title_h2.get_text(strip=True)

                # Номер выставки
                entry_num = title_elem.find("p", class_="entry-num")
                if entry_num:
                    entry_strong = entry_num.find("strong")
                    if entry_strong:
                        basic_info.entry_number = entry_strong.get_text(strip=True)

            # Стартовая цена
            price_elem = self.soup.find("p", class_="starting-price")
            if price_elem:
                price_strong = price_elem.find("strong")
                if price_strong:
                    price_em = price_strong.find("em")
                    if price_em:
                        basic_info.starting_price = (
                            price_em.get_text(strip=True) + "만원"
                        )

            # Информация из списка
            vehicle_info = self.soup.find("div", class_="vehicle-info")
            if vehicle_info:
                info_list = vehicle_info.find("ul")
                if info_list:
                    items = info_list.find_all("li")
                    for item in items:
                        title_span = item.find("span", class_="tit")
                        value_strong = item.find("strong")

                        if title_span and value_strong:
                            title = title_span.get_text(strip=True)
                            value = value_strong.get_text(strip=True)

                            if "출품일" in title:
                                basic_info.auction_date = value
                            elif "차량번호" in title:
                                # Парсим номер автомобиля и старый номер
                                car_number_match = re.search(r"^([^\(]+)", value)
                                if car_number_match:
                                    basic_info.car_number = car_number_match.group(
                                        1
                                    ).strip()

                                old_number_match = re.search(
                                    r"\(구차량번호 : ([^)]*)\)", value
                                )
                                if old_number_match:
                                    old_num = old_number_match.group(1).strip()
                                    if old_num:
                                        basic_info.old_car_number = old_num
                            elif "진행상태" in title:
                                basic_info.status = value
                            elif "평가점" in title:
                                basic_info.evaluation_score = value
                            elif "경매결과" in title:
                                basic_info.auction_result = value if value else None

        except Exception as e:
            logger.error(f"Ошибка парсинга basic_info: {e}")

        return basic_info

    def _parse_owner_info(self) -> LotteCarOwner:
        """Парсит информацию о владельце"""
        owner_info = LotteCarOwner()

        try:
            # Ищем таблицу с информацией о владельце
            tables = self.soup.find_all("table", class_="tbl-v02")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    th = row.find("th")
                    if th and "소유자" in th.get_text():
                        # Нашли секцию владельца, парсим следующие строки
                        parent_table = th.find_parent("table")
                        if parent_table:
                            owner_rows = parent_table.find_all("tr")
                            for owner_row in owner_rows:
                                cells = owner_row.find_all(["th", "td"])
                                if len(cells) >= 2:
                                    header = (
                                        cells[0].get_text(strip=True)
                                        if cells[0].name == "th"
                                        else None
                                    )
                                    if header:
                                        if "상호" in header or "명칭" in header:
                                            if len(cells) > 1:
                                                owner_info.company_name = cells[
                                                    1
                                                ].get_text(strip=True)
                                        elif "성명" in header or "대표자" in header:
                                            owner_info.representative_name = cells[
                                                1
                                            ].get_text(strip=True)
                                        elif "주민등록번호" in header:
                                            if len(cells) > 3:
                                                owner_info.registration_number = cells[
                                                    3
                                                ].get_text(strip=True)
                                        elif "주소" in header:
                                            if len(cells) > 1:
                                                owner_info.address = cells[1].get_text(
                                                    strip=True
                                                )
                        break
        except Exception as e:
            logger.error(f"Ошибка парсинга owner_info: {e}")

        return owner_info

    def _parse_technical_specs(self) -> LotteCarTechnicalSpecs:
        """Парсит технические характеристики"""
        specs = LotteCarTechnicalSpecs()

        try:
            # Ищем таблицу с детальной информацией об автомобиле
            detail_tables = self.soup.find_all("table", class_="tbl-v02")

            for table in detail_tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["th", "td"])

                    # Обрабатываем строки с двумя парами th-td
                    if len(cells) == 4:
                        # Первая пара
                        th1, td1, th2, td2 = cells
                        self._process_spec_pair(th1, td1, specs)
                        self._process_spec_pair(th2, td2, specs)

                    # Обрабатываем строки с одной парой th-td (colspan)
                    elif len(cells) >= 2:
                        th, td = cells[0], cells[1]
                        self._process_spec_pair(th, td, specs)

            # Парсим информацию из основной таблицы автомобиля
            car_tables = self.soup.find_all("table", class_="tbl-v02")
            for table in car_tables:
                rows = table.find_all("tr")
                for row in rows:
                    th = row.find("th")
                    td = row.find("td")
                    if th and td:
                        header = th.get_text(strip=True)
                        if "차명" in header:
                            specs.car_name = td.get_text(strip=True)
                        elif "차대번호" in header:
                            specs.vin_number = td.get_text(strip=True)
                        elif "검사유효기간" in header:
                            specs.inspection_valid_until = td.get_text(strip=True)
                        elif "형식·연식" in header:
                            year_text = td.get_text(strip=True)
                            if year_text and year_text.isdigit():
                                specs.year = year_text

        except Exception as e:
            logger.error(f"Ошибка парсинга technical_specs: {e}")

        return specs

    def _process_spec_pair(self, th_elem, td_elem, specs: LotteCarTechnicalSpecs):
        """Обрабатывает пару th-td для технических характеристик"""
        if not th_elem or not td_elem:
            return

        header = th_elem.get_text(strip=True)
        value = td_elem.get_text(strip=True)

        if not value:
            return

        if "차명" in header:
            specs.car_name = value
        elif "차대번호" in header:
            specs.vin_number = value
        elif "연식" in header:
            specs.year = value
        elif "주행거리" in header:
            specs.mileage = value
        elif "최초등록일" in header:
            specs.first_registration_date = value
        elif "변속기" in header:
            specs.transmission = value
        elif "용도" in header:
            specs.usage_type = value
        elif "색상" in header:
            specs.color = value
        elif "원동기형식" in header:
            specs.engine_type = value if value else None
        elif "연료" in header:
            specs.fuel_type = value
        elif "검사유효일" in header:
            specs.inspection_valid_until = value
        elif "배기량" in header:
            specs.displacement = value
        elif "차종" in header:
            specs.car_type = value
        elif "승차정원" in header:
            specs.seating_capacity = value
        elif "주요옵션" in header:
            specs.main_options = value if value else None
        elif "특이사항" in header:
            specs.special_notes = value
        elif "완비서류" in header:
            specs.complete_documents = value
        elif "보관품" in header:
            specs.stored_items = value

    def _parse_condition_check(self) -> LotteCarConditionCheck:
        """Парсит информацию о состоянии автомобиля"""
        condition = LotteCarConditionCheck()

        try:
            # Парсим таблицу состояния
            status_table = self.soup.find("table", class_="tbl-status")
            if status_table:
                tbody = status_table.find("tbody")
                if tbody:
                    row = tbody.find("tr")
                    if row:
                        cells = row.find_all("td")
                        if len(cells) >= 8:
                            condition.overall_score = cells[0].get_text(strip=True)
                            condition.engine_condition = cells[1].get_text(strip=True)
                            condition.transmission_condition = cells[2].get_text(
                                strip=True
                            )
                            condition.brake_condition = cells[3].get_text(strip=True)
                            condition.power_transmission_condition = cells[4].get_text(
                                strip=True
                            )
                            condition.air_conditioning_condition = cells[5].get_text(
                                strip=True
                            )
                            condition.steering_condition = cells[6].get_text(strip=True)
                            condition.electrical_condition = cells[7].get_text(
                                strip=True
                            )

            # Парсим детальные проверки из основной таблицы
            tables = self.soup.find_all("table", class_="tbl-v02")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    if len(cells) == 4:
                        # Обрабатываем строки с проверками устройств
                        th1, td1, th2, td2 = cells
                        self._process_condition_pair(th1, td1, condition)
                        self._process_condition_pair(th2, td2, condition)

            # Парсим изображение карты состояния
            status_map = self.soup.find("div", class_="car-status-map")
            if status_map:
                img = status_map.find("img")
                if img and img.get("src"):
                    condition.status_map_image = img["src"]

            # Парсим особые примечания из таблицы состояния
            status_section = self.soup.find("div", class_="tab-status")
            if status_section:
                spec_tables = status_section.find_all("table", class_="tbl-v02")
                for table in spec_tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        th = row.find("th")
                        td = row.find("td")
                        if th and td and "특이사항" in th.get_text():
                            condition.special_notes = td.get_text(strip=True)

        except Exception as e:
            logger.error(f"Ошибка парсинга condition_check: {e}")

        return condition

    def _process_condition_pair(
        self, th_elem, td_elem, condition: LotteCarConditionCheck
    ):
        """Обрабатывает пару th-td для проверок состояния"""
        if not th_elem or not td_elem:
            return

        header = th_elem.get_text(strip=True)
        value = td_elem.get_text(strip=True)

        if "기관장치" in header:
            condition.engine_device_check = value
        elif "동력전달장치" in header:
            condition.power_transmission_device_check = value
        elif "제동장치" in header:
            condition.brake_device_check = value
        elif "조향장치" in header:
            condition.steering_device_check = value
        elif "등화장치" in header:
            condition.lighting_device_check = value
        elif "주행장치" in header:
            condition.driving_device_check = value
        elif "축전기기계장치" in header:
            condition.electrical_device_check = value
        elif "차대번호 확인" in header:
            condition.vin_check = value
        elif "봉인 확인" in header:
            condition.seal_check = value
        elif "주소변경 확인" in header:
            condition.address_change_check = value

    def _parse_legal_status(self) -> LotteCarLegalStatus:
        """Парсит правовой статус (арест/залог)"""
        legal_status = LotteCarLegalStatus()

        try:
            # Ищем информацию о аресте/залоге
            foreclosure_elem = self.soup.find("p", class_="foreclosure-inquiry")
            if foreclosure_elem:
                spans = foreclosure_elem.find_all("span")
                for span in spans:
                    text = span.get_text(strip=True)
                    if "최종조회일자" in text:
                        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
                        if date_match:
                            legal_status.last_inquiry_date = date_match.group(1)
                    elif "압류" in text:
                        em = span.find("em")
                        if em:
                            try:
                                legal_status.seizure_count = int(
                                    em.get_text(strip=True)
                                )
                            except ValueError:
                                pass
                    elif "저당" in text:
                        em = span.find("em")
                        if em:
                            try:
                                legal_status.mortgage_count = int(
                                    em.get_text(strip=True)
                                )
                            except ValueError:
                                pass
                    elif "구변" in text:
                        em = span.find("em")
                        if em:
                            try:
                                legal_status.other_count = int(em.get_text(strip=True))
                            except ValueError:
                                pass

        except Exception as e:
            logger.error(f"Ошибка парсинга legal_status: {e}")

        return legal_status

    def _parse_media(self) -> LotteCarMedia:
        """Парсит медиа-файлы (изображения, видео)"""
        media = LotteCarMedia()

        try:
            # VR изображение
            vr_img = self.soup.find("img", id="vrImg")
            if vr_img and vr_img.get("src"):
                media.vr_image = vr_img["src"]

            # Основные изображения из слайдера
            swiper_slides = self.soup.find_all("li", class_="swiper-slide")
            for slide in swiper_slides:
                img = slide.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if src not in media.main_images:
                        media.main_images.append(src)

            # Миниатюры
            thumbnail_section = self.soup.find("div", class_="vehicle-thumbnail")
            if thumbnail_section:
                thumbnail_imgs = thumbnail_section.find_all("img")
                for img in thumbnail_imgs:
                    if img.get("src"):
                        src = img["src"]
                        if src not in media.thumbnail_images:
                            media.thumbnail_images.append(src)

            # Детальные изображения
            detail_photo_section = self.soup.find("div", class_="vehicle-photo-detail")
            if detail_photo_section:
                detail_imgs = detail_photo_section.find_all("img")
                for img in detail_imgs:
                    if img.get("src"):
                        src = img["src"]
                        if src not in media.detail_images:
                            media.detail_images.append(src)

            # Видео
            video_elem = self.soup.find("video", id="video")
            if video_elem:
                source = video_elem.find("source")
                if source and source.get("src"):
                    media.video_url = source["src"]
                    media.has_video = True

            # Проверяем, есть ли видео по наличию элементов
            yes_movie = self.soup.find("div", id="yesMovie")
            no_movie = self.soup.find("div", id="noMovie")
            if yes_movie and not no_movie:
                media.has_video = True

        except Exception as e:
            logger.error(f"Ошибка парсинга media: {e}")

        return media

    def _parse_inspection_record(self) -> LotteCarInspectionRecord:
        """Парсит запись об осмотре/проверке"""
        record = LotteCarInspectionRecord()

        try:
            # Номер записи
            paper_num = self.soup.find("div", class_="paper-num")
            if paper_num:
                record.record_number = paper_num.get_text(strip=True)

            # Дата осмотра
            paper_date = self.soup.find("div", class_="paper-date")
            if paper_date:
                record.inspection_date = paper_date.get_text(strip=True)

            # Место осмотра и инспектор
            paper_stamp = self.soup.find("div", class_="paper-stamp")
            if paper_stamp:
                stamp_text = paper_stamp.get_text(strip=True)
                lines = stamp_text.split("\n")
                if len(lines) >= 1:
                    record.inspection_location = lines[0].strip()
                if len(lines) >= 2:
                    record.inspector_name = lines[1].strip()

            # Проверки идентичности
            identity_section = self.soup.find(
                "td",
                string=lambda text: text
                and "차대번호" in text
                and "원동기형식" in text,
            )
            if identity_section:
                checkboxes = identity_section.find_all("input", type="checkbox")
                for checkbox in checkboxes:
                    if checkbox.get("checked") is not None:
                        label = checkbox.find_next("label")
                        if label:
                            label_text = label.get_text(strip=True)
                            if "차대번호" in label_text:
                                record.identity_check_vin = True
                            elif "원동기형식" in label_text:
                                record.identity_check_engine = True

            # Проверка регистрации
            reg_check_row = None
            tables = self.soup.find_all("table", class_="tbl-v02")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    th = row.find("th")
                    if th and "등록사항 확인" in th.get_text():
                        td = row.find("td")
                        if td:
                            record.registration_check = td.get_text(strip=True)
                        break

        except Exception as e:
            logger.error(f"Ошибка парсинга inspection_record: {e}")

        return record

    def _parse_management_data(self) -> Dict[str, Optional[str]]:
        """Парсит управленческие данные из скрытых полей формы"""
        data = {
            "management_number": None,
            "management_division": None,
            "exhibition_sequence": None,
        }

        try:
            # Ищем скрытые поля в формах
            forms = self.soup.find_all("form")
            for form in forms:
                inputs = form.find_all("input", type="hidden")
                for input_elem in inputs:
                    name = input_elem.get("name", "")
                    value = input_elem.get("value", "")

                    if "searchMngNo" in name or "mngNo" in name:
                        data["management_number"] = value
                    elif "searchMngDivCd" in name or "mngDivCd" in name:
                        data["management_division"] = value
                    elif "searchExhiRegiSeq" in name or "exhiRegiSeq" in name:
                        data["exhibition_sequence"] = value

        except Exception as e:
            logger.error(f"Ошибка парсинга management_data: {e}")

        return data


def parse_lotte_car_detail(
    html_content: str, source_url: Optional[str] = None
) -> LotteCarDetail:
    """
    Главная функция для парсинга детальной страницы автомобиля Lotte

    Args:
        html_content: HTML контент страницы
        source_url: URL источника

    Returns:
        LotteCarDetail: Полная информация об автомобиле
    """
    parser = LotteCarDetailParser()
    return parser.parse(html_content, source_url)
