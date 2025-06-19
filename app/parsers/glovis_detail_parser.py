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

        # Инициализируем переменные
        first_registration = fuel_type = mileage = transmission = color = (
            auction_status
        ) = None
        year = None

        if spec_desc:
            # Ищем все элементы li в spec-desc
            li_elements = spec_desc.find_all("li")

            for li in li_elements:
                text = li.get_text()

                # Первый li содержит основную информацию
                if "출품 차량은" in text:
                    # Извлекаем данные из первого li
                    year_match = re.search(r"최초등록일\s*([^,]+)", text)
                    if year_match:
                        first_registration = self._clean_text(year_match.group(1))
                        # Извлекаем год из даты
                        year_extract = re.search(r"(\d{4})년", first_registration)
                        if year_extract:
                            year = year_extract.group(1)

                    fuel_match = re.search(r"연료\s*([^,]+)", text)
                    if fuel_match:
                        fuel_type = self._clean_text(fuel_match.group(1))

                    mileage_match = re.search(r"주행거리\s*([0-9,]+km)", text)
                    if mileage_match:
                        mileage = self._clean_text(mileage_match.group(1))

                    transmission_match = re.search(r"변속기\s*([^,]+)", text)
                    if transmission_match:
                        transmission = self._clean_text(transmission_match.group(1))

                    color_match = re.search(r"색상\s*([^입니다]+)", text)
                    if color_match:
                        color = self._clean_text(color_match.group(1))

                # Второй li содержит статус аукциона
                elif "해당 차량은" in text:
                    status_match = re.search(r"해당 차량은\s*([^차량]+차량)", text)
                    if status_match:
                        auction_status = self._clean_text(status_match.group(1))

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

        # Ищем все dl элементы
        dl_elements = pricing_section.find_all("dl")

        if dl_elements:
            # В Glovis все цены находятся в одном dl
            dl = dl_elements[0]
            dt_elements = dl.find_all("dt")
            dd_elements = dl.find_all("dd")

            for dt, dd in zip(dt_elements, dd_elements):
                label = self._clean_text(dt.get_text())
                logger.info(f"💰 Проверяем label: '{label}'")

                if "신차가격" in label:
                    price_span = dd.find("span", class_="price")
                    if price_span:
                        new_car_price = self._clean_text(price_span.get_text())
                        logger.info(f"✅ Найдена цена нового авто: {new_car_price}")

                elif "차량출고가" in label:
                    price_span = dd.find("span", class_="price")
                    if price_span:
                        estimated_price = self._clean_text(price_span.get_text())
                        logger.info(f"✅ Найдена цена с опциями: {estimated_price}")
                    else:
                        logger.info(f"❌ Не найден span с ценой для label: {label}")

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

                    # Особая обработка для полей с кнопками
                    if key == "차량번호":
                        # Извлекаем только номер, убираем текст кнопки
                        car_num_match = re.search(r"([\d가-힣]+)", value)
                        if car_num_match:
                            value = car_num_match.group(1)
                    elif key == "차대번호":
                        # Извлекаем только номер шасси
                        chassis_match = re.search(r"([A-Z0-9]+)", value)
                        if chassis_match:
                            value = chassis_match.group(1)
                    elif key == "완비서류":
                        # Убираем текст ссылки "구비서류 안내"
                        value = re.sub(r"구비서류\s*안내", "", value).strip()

                    specs_data[key] = value

        # Дополнительно ищем информацию в spec-desc для недостающих данных
        spec_desc = self.soup.find("div", class_="spec-desc")
        if spec_desc:
            # Парсим информацию из spec-desc если она не найдена в specs_data
            li_elements = spec_desc.find_all("li")
            for li in li_elements:
                text = li.get_text()

                if "최초등록일" in text and "최초등록일" not in specs_data:
                    reg_match = re.search(r"최초등록일\s*([^,]+)", text)
                    if reg_match:
                        specs_data["최초등록일"] = self._clean_text(reg_match.group(1))

                if "주행거리" in text and "주행거리" not in specs_data:
                    mileage_match = re.search(r"주행거리\s*([0-9,]+km)", text)
                    if mileage_match:
                        specs_data["주행거리"] = self._clean_text(
                            mileage_match.group(1)
                        )

                if "색상" in text and "색상" not in specs_data:
                    color_match = re.search(r"색상\s*([^입니다]+)", text)
                    if color_match:
                        specs_data["색상"] = self._clean_text(color_match.group(1))

                if "변속기" in text and "변속기" not in specs_data:
                    trans_match = re.search(r"변속기\s*([^,]+)", text)
                    if trans_match:
                        specs_data["변속기"] = self._clean_text(trans_match.group(1))

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

        # Ищем секцию с результатами проверки
        perf_section = self.soup.find("div", class_="spec-box spec02")
        if not perf_section:
            return None

        # Ищем таблицу с результатами проверки
        perf_table = perf_section.find("div", class_="table-box type01")
        if not perf_table:
            return None

        table = perf_table.find("table")
        if not table:
            return None

        # Парсим данные из tbody
        performance_data = {}
        tbody = table.find("tbody")
        if tbody:
            rows = tbody.find_all("tr")
            for row in rows:
                th_elements = row.find_all("th")
                td_elements = row.find_all("td")

                # Парсим пары th-td
                for th, td in zip(th_elements, td_elements):
                    key = self._clean_text(th.get_text())
                    value = self._clean_text(td.get_text())
                    performance_data[key] = value

        # Ищем дополнительную таблицу с особыми замечаниями
        additional_table = perf_section.find("div", class_="table-box type02")
        special_notes = changes = evaluation_opinion = None

        if additional_table:
            rows = additional_table.find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")

                if th and td:
                    label = self._clean_text(th.get_text())
                    value = self._clean_text(td.get_text())

                    if "특이사항" in label:
                        special_notes = value if value and value != "-" else None
                    elif "변경사항" in label:
                        changes = value if value and value != "-" else None
                    elif "평가의견" in label:
                        evaluation_opinion = value if value and value != "-" else None

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

        # Ищем секцию с опциями в new-car-info
        options_section = self.soup.find("div", class_="new-car-info")
        if not options_section:
            return None

        options_text = None
        options_list = []

        # Ищем dl с опциями
        dl_elements = options_section.find_all("dl")
        for dl in dl_elements:
            dt = dl.find("dt")
            dd = dl.find("dd")

            if dt and dd and "옵션 장착 현황" in dt.get_text():
                options_div = dd.find("div", class_="option")
                if options_div:
                    options_text = self._clean_text(options_div.get_text())

                    # Разбираем опции по запятым
                    if options_text and options_text != "-":
                        # Убираем начальный "-" и разбиваем по запятым
                        cleaned_text = options_text.lstrip("- ").strip()
                        if cleaned_text:
                            options_list = [
                                opt.strip()
                                for opt in cleaned_text.split(",")
                                if opt.strip()
                            ]

        # Также проверяем секцию spec03 для опций
        options_spec_section = self.soup.find("div", class_="spec-box spec03")
        if options_spec_section and not options_list:
            # Здесь может быть дополнительная информация об опциях
            pass

        return GlovisCarOptions(
            standard_options=options_list, all_options_text=options_text
        )

    def _parse_images(self) -> List[GlovisCarImage]:
        """Парсинг изображений автомобиля"""
        logger.debug("📷 Парсинг изображений автомобиля")

        images = []
        seen_urls = set()  # Для избежания дубликатов

        # Ищем изображения в swiper
        swiper_slides = self.soup.find_all("div", class_="swiper-slide")
        for slide in swiper_slides:
            img = slide.find("img")
            if img and img.get("src"):
                url = img.get("src")

                # Пропускаем дубликаты
                if url in seen_urls:
                    continue

                seen_urls.add(url)
                alt_text = img.get("alt", "")

                images.append(GlovisCarImage(url=url, alt_text=alt_text))

        logger.debug(f"📷 Найдено {len(images)} уникальных изображений")
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

        # Паттерн для извлечения производителя в квадратных скобках
        manufacturer_match = re.search(r"\[([^\]]+)\]", name)
        if manufacturer_match:
            manufacturer = manufacturer_match.group(1)
            # Убираем производителя из названия для дальнейшего парсинга
            remaining = name.replace(f"[{manufacturer}]", "").strip()
        else:
            # Если нет квадратных скобок, первое слово - производитель
            parts = name.split()
            if not parts:
                return "", "", None
            manufacturer = parts[0]
            remaining = " ".join(parts[1:]) if len(parts) > 1 else ""

        # Разбираем оставшуюся часть
        if not remaining:
            return manufacturer, "", None

        # Обычно второе слово (или первые несколько слов) - это модель
        remaining_parts = remaining.split()
        if not remaining_parts:
            return manufacturer, "", None

        # Попытаемся определить модель и комплектацию
        # Часто модель состоит из 1-2 слов, остальное - комплектация
        if len(remaining_parts) == 1:
            return manufacturer, remaining_parts[0], None
        elif len(remaining_parts) == 2:
            return manufacturer, " ".join(remaining_parts[:2]), None
        else:
            # Берем первые 2 слова как модель, остальное как комплектацию
            model = " ".join(remaining_parts[:2])
            grade = " ".join(remaining_parts[2:])
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
