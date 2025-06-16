"""
Парсер для детальной страницы автомобиля Glovis
"""

import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag
from datetime import datetime

from app.models.glovis_detail import (
    GlovisCarDetail,
    GlovisCarBasicInfo,
    GlovisCarPricing,
    GlovisCarDetailedSpecs,
    GlovisCarPerformanceCheck,
    GlovisCarOptions,
    GlovisCarImage,
    GlovisCarAdditionalInfo,
    GlovisCarAccidentHistory,
    GlovisCarInspectionDetails,
)
from app.core.logging import get_logger

logger = get_logger("glovis_detail_parser")


class GlovisDetailParser:
    """Парсер детальной страницы автомобиля Glovis"""

    def __init__(self):
        self.soup: Optional[BeautifulSoup] = None

    def parse(
        self, html_content: str, source_url: Optional[str] = None
    ) -> GlovisCarDetail:
        """
        Парсинг HTML страницы автомобиля

        Args:
            html_content: HTML контент страницы
            source_url: URL источника

        Returns:
            GlovisCarDetail: Детальная информация об автомобиле
        """
        logger.info("🔍 Начинаем парсинг детальной страницы автомобиля")

        try:
            self.soup = BeautifulSoup(html_content, "html.parser")

            # Парсим основные разделы
            basic_info = self._parse_basic_info()
            pricing = self._parse_pricing()
            detailed_specs = self._parse_detailed_specs()
            performance_check = self._parse_performance_check()
            options = self._parse_options()
            images = self._parse_images()
            additional_info = self._parse_additional_info()

            # Извлекаем ID автомобиля и номер аукциона из URL
            car_id, auction_number = self._extract_ids_from_url(source_url)

            result = GlovisCarDetail(
                basic_info=basic_info,
                pricing=pricing,
                detailed_specs=detailed_specs,
                performance_check=performance_check,
                options=options,
                images=images,
                additional_info=additional_info,
                parsed_at=datetime.now(),
                source_url=source_url,
                car_id=car_id,
                auction_number=auction_number,
            )

            logger.info(f"✅ Парсинг завершен: {basic_info.name}")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге: {str(e)}")
            raise

    def _parse_basic_info(self) -> GlovisCarBasicInfo:
        """Парсинг базовой информации об автомобиле"""
        logger.debug("📋 Парсинг базовой информации")

        # Название автомобиля
        name_elem = self.soup.find("h2", class_="car-name")
        name = self._clean_text(name_elem.get_text()) if name_elem else ""

        # Разбираем название на составляющие
        manufacturer, model, grade = self._parse_car_name(name)

        # Информация из описания
        spec_desc = self.soup.find("div", class_="spec-desc")
        if spec_desc:
            desc_text = spec_desc.get_text()

            # Извлекаем данные из описания
            year_match = re.search(
                r"최초등록일\s*(\d{4}년\s*\d{2}월\s*\d{2}일)", desc_text
            )
            fuel_match = re.search(r"연료\s*([^,]+)", desc_text)
            mileage_match = re.search(r"주행거리\s*([^,]+)", desc_text)
            transmission_match = re.search(r"변속기\s*([^,]+)", desc_text)
            color_match = re.search(r"색상\s*([^)]+)", desc_text)
            status_match = re.search(r"해당 차량은\s*([^)]+)", desc_text)

            first_registration = year_match.group(1).strip() if year_match else None
            fuel_type = fuel_match.group(1).strip() if fuel_match else None
            mileage = mileage_match.group(1).strip() if mileage_match else None
            transmission = (
                transmission_match.group(1).strip() if transmission_match else None
            )
            color = color_match.group(1).strip() if color_match else None
            auction_status = status_match.group(1).strip() if status_match else None
        else:
            first_registration = fuel_type = mileage = transmission = color = (
                auction_status
            ) = None

        # Определяем год из даты регистрации
        year = None
        if first_registration:
            year_match = re.search(r"(\d{4})", first_registration)
            year = year_match.group(1) if year_match else None

        return GlovisCarBasicInfo(
            name=name,
            manufacturer=manufacturer,
            model=model,
            grade=grade,
            year=year,
            first_registration_date=first_registration,
            fuel_type=fuel_type,
            mileage=mileage,
            transmission=transmission,
            color=color,
            auction_status=auction_status,
        )

    def _parse_pricing(self) -> Optional[GlovisCarPricing]:
        """Парсинг информации о ценах"""
        logger.debug("💰 Парсинг информации о ценах")

        pricing_section = self.soup.find("div", class_="new-car-info")
        if not pricing_section:
            return None

        new_car_price = None
        estimated_price = None

        # Ищем цену нового автомобиля
        price_spans = pricing_section.find_all("span", class_="price")
        if price_spans:
            new_car_price = self._clean_text(price_spans[0].get_text())
            if len(price_spans) > 1:
                estimated_price = self._clean_text(price_spans[1].get_text())

        # Пока не парсим активные цены торгов, так как это требует JavaScript
        return GlovisCarPricing(
            new_car_price=new_car_price, estimated_price=estimated_price
        )

    def _parse_detailed_specs(self) -> Optional[GlovisCarDetailedSpecs]:
        """Парсинг детальных характеристик"""
        logger.debug("🔧 Парсинг детальных характеристик")

        # Ищем секцию с информацией о автомобиле
        specs_section = self.soup.find("div", class_="spec-box spec01")
        if not specs_section:
            return None

        specs_data = {}

        # Парсим все пары dt/dd в секции
        info_boxes = specs_section.find_all("div", class_="info-box")
        for info_box in info_boxes:
            dl_elements = info_box.find_all("dl")
            for dl in dl_elements:
                dt_elements = dl.find_all("dt")
                dd_elements = dl.find_all("dd")

                for dt, dd in zip(dt_elements, dd_elements):
                    key = self._clean_text(dt.get_text())
                    value = self._clean_text(dd.get_text())
                    specs_data[key] = value

        return GlovisCarDetailedSpecs(
            product_category=specs_data.get("상품구분"),
            fuel_type=specs_data.get("연료"),
            engine_displacement=specs_data.get("배기량"),
            seating_capacity=specs_data.get("인승"),
            usage_purpose=specs_data.get("용도/구분"),
            engine_type=specs_data.get("원동기형식"),
            accessories=specs_data.get("보관품"),
            inspection_date=specs_data.get("정기검사일"),
            complete_documents=specs_data.get("완비서류"),
            car_number=specs_data.get("차량번호"),
            chassis_number=specs_data.get("차대번호"),
            model_year=specs_data.get("연식"),
            first_registration=specs_data.get("최초등록일"),
            mileage=specs_data.get("주행거리"),
            color_full=specs_data.get("색상"),
            transmission=specs_data.get("변속기"),
            lot_number=specs_data.get("자리번호"),
            missing_documents=specs_data.get("미비서류"),
        )

    def _parse_performance_check(self) -> Optional[GlovisCarPerformanceCheck]:
        """Парсинг результатов технической проверки"""
        logger.debug("🔍 Парсинг результатов технической проверки")

        # Ищем таблицу с результатами проверки
        perf_table = self.soup.find("div", class_="table-box type01")
        if not perf_table:
            return None

        table = perf_table.find("table")
        if not table:
            return None

        # Парсим заголовки
        headers = []
        thead = table.find("thead")
        if thead:
            th_elements = thead.find_all("th")
            headers = [self._clean_text(th.get_text()) for th in th_elements]

        # Парсим данные
        performance_data = {}
        tbody = table.find("tbody")
        if tbody:
            rows = tbody.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) == len(headers):
                    for header, cell in zip(headers, cells):
                        value = self._clean_text(cell.get_text())
                        performance_data[header] = value

        # Ищем дополнительную таблицу с особыми замечаниями
        additional_table = self.soup.find("div", class_="table-box type02")
        special_notes = changes = evaluation_opinion = None

        if additional_table:
            rows = additional_table.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    label = self._clean_text(cells[0].get_text())
                    value = self._clean_text(cells[1].get_text())

                    if "특이사항" in label:
                        special_notes = value
                    elif "변경사항" in label:
                        changes = value
                    elif "평가의견" in label:
                        evaluation_opinion = value

        return GlovisCarPerformanceCheck(
            engine=performance_data.get("기관"),
            braking=performance_data.get("제동"),
            steering=performance_data.get("조향"),
            electrical=performance_data.get("전기"),
            transmission=performance_data.get("변속"),
            air_conditioning=performance_data.get("공조"),
            power=performance_data.get("동력"),
            interior=performance_data.get("실내"),
            lighting=performance_data.get("등화"),
            rating=performance_data.get("평가점"),
            special_notes=special_notes,
            changes=changes,
            evaluation_opinion=evaluation_opinion,
        )

    def _parse_options(self) -> Optional[GlovisCarOptions]:
        """Парсинг опций автомобиля"""
        logger.debug("⚙️ Парсинг опций автомобиля")

        # Ищем секцию с опциями
        options_section = self.soup.find("div", class_="new-car-info")
        if not options_section:
            return None

        options_div = options_section.find("div", class_="option")
        if not options_div:
            return None

        options_text = self._clean_text(options_div.get_text())

        # Разбираем опции по запятым
        options_list = []
        if options_text and options_text != "-":
            # Убираем начальный "-" и разбиваем по запятым
            cleaned_text = options_text.lstrip("- ").strip()
            if cleaned_text:
                options_list = [
                    opt.strip() for opt in cleaned_text.split(",") if opt.strip()
                ]

        return GlovisCarOptions(
            standard_options=options_list, all_options_text=options_text
        )

    def _parse_images(self) -> List[GlovisCarImage]:
        """Парсинг изображений автомобиля"""
        logger.debug("📷 Парсинг изображений автомобиля")

        images = []

        # Ищем изображения в swiper
        swiper_slides = self.soup.find_all("div", class_="swiper-slide")
        for slide in swiper_slides:
            img = slide.find("img")
            if img and img.get("src"):
                url = img.get("src")
                alt_text = img.get("alt", "")

                images.append(GlovisCarImage(url=url, alt_text=alt_text))

        logger.debug(f"📷 Найдено {len(images)} изображений")
        return images

    def _parse_additional_info(self) -> Optional[GlovisCarAdditionalInfo]:
        """Парсинг дополнительной информации"""
        logger.debug("ℹ️ Парсинг дополнительной информации")

        # Пока возвращаем базовую структуру
        # В будущем можно добавить парсинг дополнительных секций
        return GlovisCarAdditionalInfo()

    def _parse_car_name(self, name: str) -> tuple[str, str, Optional[str]]:
        """
        Разбор названия автомобиля на составляющие

        Args:
            name: Полное название автомобиля

        Returns:
            tuple: (производитель, модель, комплектация)
        """
        if not name:
            return "", "", None

        # Убираем квадратные скобки и лишние пробелы
        clean_name = re.sub(r"\[|\]", "", name).strip()

        # Разбиваем по пробелам
        parts = clean_name.split()

        if len(parts) == 0:
            return "", "", None
        elif len(parts) == 1:
            return parts[0], "", None
        elif len(parts) == 2:
            return parts[0], parts[1], None
        else:
            # Первое слово - производитель, второе - модель, остальное - комплектация
            manufacturer = parts[0]
            model = parts[1]
            grade = " ".join(parts[2:])
            return manufacturer, model, grade

    def _extract_ids_from_url(
        self, url: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Извлечение ID автомобиля и номера аукциона из URL

        Args:
            url: URL страницы автомобиля

        Returns:
            tuple: (car_id, auction_number)
        """
        if not url:
            return None, None

        car_id = None
        auction_number = None

        # Извлекаем параметры из URL
        gn_match = re.search(r"gn=([^&]+)", url)
        if gn_match:
            car_id = gn_match.group(1)

        atn_match = re.search(r"atn=([^&]+)", url)
        if atn_match:
            auction_number = atn_match.group(1)

        return car_id, auction_number

    def _clean_text(self, text: str) -> str:
        """
        Очистка текста от лишних символов и пробелов

        Args:
            text: Исходный текст

        Returns:
            str: Очищенный текст
        """
        if not text:
            return ""

        # Убираем лишние пробелы и переносы строк
        cleaned = re.sub(r"\s+", " ", text).strip()

        # Убираем специальные символы в начале и конце
        cleaned = cleaned.strip("- \t\n\r")

        return cleaned

    def _safe_find_text(
        self, element: Optional[Tag], selector: str, default: str = ""
    ) -> str:
        """
        Безопасный поиск текста в элементе

        Args:
            element: HTML элемент
            selector: CSS селектор
            default: Значение по умолчанию

        Returns:
            str: Найденный текст или значение по умолчанию
        """
        if not element:
            return default

        found = element.select_one(selector)
        if found:
            return self._clean_text(found.get_text())
        return default
