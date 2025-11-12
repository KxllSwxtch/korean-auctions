import json
from typing import List, Dict, Any, Optional
from loguru import logger

from app.models.kcar import (
    KCarCar,
    KCarResponse,
    KCarStatsResponse,
    KCarDetailedCar,
    KCarDetailResponse,
    KCarModelsResponse,
    KCarGenerationsResponse,
    KCarSearchResponse,
    TechnicalSheet,
    TechnicalSheetInspection,
)


class KCarParser:
    """Парсер для обработки JSON ответов от KCar API"""

    def __init__(self):
        self.name = "KCar Parser"
        logger.info(f"🔧 {self.name} инициализирован")

    def parse_cars_json(
        self,
        json_data: Dict[str, Any],
        page: int = 1,
        page_size: int = 50,
        total_count: Optional[int] = None,
    ) -> KCarResponse:
        """
        Парсинг JSON ответа со списком автомобилей

        Args:
            json_data: JSON данные от KCar API
            page: Номер страницы
            page_size: Размер страницы
            total_count: Общее количество автомобилей

        Returns:
            KCarResponse с списком автомобилей
        """
        try:
            logger.info(f"📊 {self.name}: Начинаю парсинг JSON данных")

            cars = []
            car_list = json_data.get("CAR_LIST", [])

            logger.info(f"📋 Найдено {len(car_list)} автомобилей в JSON")

            for car_data in car_list:
                try:
                    car = self._parse_single_car(car_data)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга автомобиля: {e}")
                    continue

            # Извлекаем информацию о запросе
            auction_req_vo = json_data.get("auctionReqVo", {})

            # Рассчитываем поля пагинации
            actual_total_count = total_count if total_count is not None else len(cars)
            total_pages = None
            has_next_page = False
            has_prev_page = page > 1

            if actual_total_count > 0:
                total_pages = (actual_total_count + page_size - 1) // page_size
                has_next_page = page < total_pages

            response = KCarResponse(
                auction_req_vo=auction_req_vo,
                car_list=cars,
                total_count=actual_total_count,
                current_page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next_page=has_next_page,
                has_prev_page=has_prev_page,
                success=True,
                message=f"Успешно обработано {len(cars)} автомобилей",
            )

            logger.success(
                f"✅ {self.name}: Успешно обработано {len(cars)} автомобилей (страница {page}/{total_pages})"
            )
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка парсинга JSON: {e}")
            return KCarResponse(
                car_list=[],
                total_count=0,
                current_page=page,
                page_size=page_size,
                total_pages=1,
                has_next_page=False,
                has_prev_page=page > 1,
                success=False,
                message=f"Ошибка парсинга: {str(e)}",
            )

    def _parse_single_car(self, car_data: Dict[str, Any]) -> Optional[KCarCar]:
        """
        Парсинг данных одного автомобиля

        Args:
            car_data: Данные автомобиля из JSON

        Returns:
            KCarCar объект или None при ошибке
        """
        try:
            # Создаем объект автомобиля напрямую из JSON данных
            # Pydantic автоматически обработает алиасы полей
            car = KCarCar(**car_data)

            # Обрабатываем URL изображений - формируем полные пути
            if car.thumbnail:
                # Проверяем, если уже есть полный URL
                if car.thumbnail.startswith("http"):
                    pass  # Оставляем как есть
                elif car.thumbnail.startswith("/FILE_UPLOAD"):
                    # Уже полный путь, добавляем только домен
                    car.thumbnail = f"https://www.kcarauction.com{car.thumbnail}"
                else:
                    # Убираем суффиксы качества (_370, _640) для получения оригинала
                    clean_thumbnail = car.thumbnail
                    if "_370" in clean_thumbnail:
                        clean_thumbnail = clean_thumbnail.replace("_370", "")
                    elif "_640" in clean_thumbnail:
                        clean_thumbnail = clean_thumbnail.replace("_640", "")

                    # Формируем полный путь
                    car.thumbnail = f"https://www.kcarauction.com/auction/IMAGE_UPLOAD/CAR/{clean_thumbnail}"

            if car.thumbnail_mobile:
                # Проверяем, если уже есть полный URL
                if car.thumbnail_mobile.startswith("http"):
                    pass  # Оставляем как есть
                elif car.thumbnail_mobile.startswith("/FILE_UPLOAD"):
                    # Уже полный путь, добавляем только домен
                    car.thumbnail_mobile = (
                        f"https://www.kcarauction.com{car.thumbnail_mobile}"
                    )
                else:
                    # Убираем суффиксы качества (_370, _640) для получения оригинала
                    clean_thumbnail_mobile = car.thumbnail_mobile.lstrip("/")
                    if "_370" in clean_thumbnail_mobile:
                        clean_thumbnail_mobile = clean_thumbnail_mobile.replace(
                            "_370", ""
                        )
                    elif "_640" in clean_thumbnail_mobile:
                        clean_thumbnail_mobile = clean_thumbnail_mobile.replace(
                            "_640", ""
                        )

                    # Формируем полный путь
                    car.thumbnail_mobile = f"https://www.kcarauction.com/auction/IMAGE_UPLOAD/CAR/{clean_thumbnail_mobile}"

            # Логируем основную информацию об автомобиле
            car_info = (
                f"ID: {car.car_id}, Название: {car.car_name}, Номер: {car.car_number}"
            )
            if car.thumbnail:
                car_info += f", Фото: {car.thumbnail}"

            logger.debug(f"🚗 Обработан автомобиль: {car_info}")

            return car

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга автомобиля: {e}")
            logger.debug(f"🔍 Данные автомобиля: {car_data}")
            return None

    def calculate_stats(self, cars: List[KCarCar]) -> KCarStatsResponse:
        """
        Расчет статистики по автомобилям

        Args:
            cars: Список автомобилей

        Returns:
            KCarStatsResponse со статистикой
        """
        try:
            logger.info(
                f"📊 {self.name}: Расчет статистики для {len(cars)} автомобилей"
            )

            total_cars = len(cars)
            daily_auctions = 0
            weekly_auctions = 0
            locations = set()
            manufacturers = set()
            prices = []

            for car in cars:
                # Подсчет типов аукционов (теперь только weekly)
                if car.auction_type_desc and "WEEKLY" in car.auction_type_desc.upper():
                    weekly_auctions += 1
                elif car.auction_type_desc and "DAILY" in car.auction_type_desc.upper():
                    daily_auctions += 1

                # Сбор локаций
                if car.car_location:
                    locations.add(car.car_location)
                if car.auction_place_name:
                    locations.add(car.auction_place_name)

                # Извлечение производителей из названий автомобилей
                if car.car_name:
                    # Пытаемся извлечь производителя (первое слово)
                    first_word = car.car_name.split()[0] if car.car_name.split() else ""
                    if first_word:
                        manufacturers.add(first_word)

                # Сбор цен для расчета средней
                if car.auction_start_price and car.auction_start_price.isdigit():
                    prices.append(float(car.auction_start_price))
                elif car.auction_start_hope and car.auction_start_hope.isdigit():
                    prices.append(float(car.auction_start_hope))

            # Расчет средней цены
            average_price = sum(prices) / len(prices) if prices else None

            stats = KCarStatsResponse(
                total_cars=total_cars,
                daily_auctions=daily_auctions,
                weekly_auctions=weekly_auctions,
                locations=list(locations),
                manufacturers=list(manufacturers),
                average_price=average_price,
                success=True,
            )

            logger.success(f"✅ {self.name}: Статистика рассчитана успешно")
            return stats

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка расчета статистики: {e}")
            return KCarStatsResponse(success=False)

    def generate_test_data(self, count: int = 10) -> KCarResponse:
        """
        Генерация тестовых данных

        Args:
            count: Количество тестовых автомобилей

        Returns:
            KCarResponse с тестовыми данными
        """
        try:
            logger.info(f"🧪 {self.name}: Генерация {count} тестовых автомобилей")

            test_cars = []

            # Расширенные шаблоны автомобилей с корректными моделями
            test_templates = [
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "현대 소나타 2.0 하이브리드 {} 모델",
                    "CNO": "{}서{:04d}",
                    "AUC_STRT_PRC": "{}200000",
                    "AUC_STAT_NM": "위클리 대기",
                    "FORM_YR": "202{}",
                    "MILG": "{}0000",
                    "FUEL_CD": "하이브리드",
                    "GBOX_DCD": "오토",
                    "EXTERIOR_COLOR_NM": "진주백",
                    "AUC_PLC_NM": "서울경매장",
                    "EXBIT_SEQ": "{}",
                    "MNUFTR_CD": "001_001",  # Hyundai
                    "MODEL_GRP_CD": "018",  # Sonata
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "현대 그랜저 3.3 V6 {} 모델",
                    "CNO": "{}나{:04d}",
                    "AUC_STRT_PRC": "{}500000",
                    "AUC_STAT_NM": "위클리 진행",
                    "FORM_YR": "202{}",
                    "MILG": "{}5000",
                    "FUEL_CD": "휘발유",
                    "GBOX_DCD": "오토",
                    "EXTERIOR_COLOR_NM": "진주흑",
                    "AUC_PLC_NM": "수원경매장",
                    "EXBIT_SEQ": "{}",
                    "MNUFTR_CD": "001_001",  # Hyundai
                    "MODEL_GRP_CD": "008",  # Grandeur
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "기아 K5 2.0 LPi {} 모델",
                    "CNO": "{}다{:04d}",
                    "AUC_STRT_PRC": "{}800000",
                    "AUC_STAT_NM": "위클리 완료",
                    "FORM_YR": "202{}",
                    "MILG": "{}2000",
                    "FUEL_CD": "LPG",
                    "GBOX_DCD": "수동",
                    "EXTERIOR_COLOR_NM": "은색",
                    "AUC_PLC_NM": "안산경매장",
                    "EXBIT_SEQ": "{}",
                    "MNUFTR_CD": "002_001",  # Kia
                    "MODEL_GRP_CD": "020",  # K5
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "현대 아반떼 1.6 MPI {} 모델",
                    "CNO": "{}라{:04d}",
                    "AUC_STRT_PRC": "{}400000",
                    "AUC_STAT_NM": "위클리 대기",
                    "FORM_YR": "202{}",
                    "MILG": "{}8000",
                    "FUEL_CD": "휘발유",
                    "GBOX_DCD": "오토",
                    "EXTERIOR_COLOR_NM": "흰색",
                    "AUC_PLC_NM": "부산경매장",
                    "EXBIT_SEQ": "{}",
                    "MNUFTR_CD": "001_001",  # Hyundai
                    "MODEL_GRP_CD": "002",  # Avante
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "쌍용 렉스턴 2.2 디젤 {} 모델",
                    "CNO": "{}마{:04d}",
                    "AUC_STRT_PRC": "{}600000",
                    "AUC_STAT_NM": "위클리 진행",
                    "FORM_YR": "202{}",
                    "MILG": "{}5000",
                    "FUEL_CD": "경유",
                    "GBOX_DCD": "오토",
                    "EXTERIOR_COLOR_NM": "검은색",
                    "AUC_PLC_NM": "광주경매장",
                    "EXBIT_SEQ": "{}",
                    "MNUFTR_CD": "013_001",  # SsangYong
                    "MODEL_GRP_CD": "080",  # Rexton
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "현대 투싼 1.6 터보 {} 모델",
                    "CNO": "{}바{:04d}",
                    "AUC_STRT_PRC": "{}300000",
                    "AUC_STAT_NM": "위클리 대기",
                    "FORM_YR": "202{}",
                    "MILG": "{}1000",
                    "FUEL_CD": "휘발유",
                    "GBOX_DCD": "오토",
                    "EXTERIOR_COLOR_NM": "회색",
                    "AUC_PLC_NM": "대구경매장",
                    "EXBIT_SEQ": "{}",
                    "MNUFTR_CD": "001_001",  # Hyundai
                    "MODEL_GRP_CD": "025",  # Tucson
                },
            ]

            for i in range(count):
                template = test_templates[i % len(test_templates)]
                car_data = {}

                for key, value in template.items():
                    if "{}" in str(value):
                        if key in ["CAR_ID"]:
                            car_data[key] = value.format(1000 + i)
                        elif key in ["CAR_NM"]:
                            car_data[key] = value.format(2020 + (i % 5))
                        elif key in ["CNO"]:
                            car_data[key] = value.format(10 + (i % 90), 1000 + i)
                        elif key in ["AUC_STRT_PRC"]:
                            car_data[key] = value.format(1 + (i % 9))
                        elif key in ["FORM_YR"]:
                            car_data[key] = value.format(0 + (i % 5))
                        elif key in ["MILG"]:
                            car_data[key] = value.format(1 + (i % 9))
                        elif key in ["EXBIT_SEQ"]:
                            car_data[key] = value.format(1000 + i)
                    else:
                        car_data[key] = value

                # Добавляем дополнительные поля
                car_data.update(
                    {
                        "AUC_CD": f"AC2025{(600 + i):04d}",
                        "AUC_STRT_DT": "2025-01-15",
                        "ENGDISPMNT": f"{1500 + (i * 100)}cc",
                        "CAR_POINT": f"{8.0 + (i % 2)}",
                        "CAR_LOCT": "서울특별시",
                        "THUMBNAIL": f"/images/test/car_{1000 + i}.jpg",
                    }
                )

                test_cars.append(car_data)

            # Парсим тестовые данные
            response = self.parse_cars_json(
                {"CAR_LIST": test_cars}, page=1, page_size=count, total_count=count
            )
            logger.success(f"✅ {self.name}: Генерация тестовых данных завершена")
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка генерации тестовых данных: {e}")
            return KCarResponse(
                car_list=[],
                total_count=0,
                success=False,
                message=f"Ошибка генерации: {str(e)}",
            )

    def parse_car_detail_html(
        self, html_content: str, car_id: str, auction_code: str
    ) -> "KCarDetailResponse":
        """
        Парсинг HTML страницы с детальной информацией об автомобиле

        Args:
            html_content: HTML контент страницы
            car_id: ID автомобиля
            auction_code: Код аукциона

        Returns:
            KCarDetailResponse с детальной информацией
        """
        try:
            logger.info(
                f"🔍 {self.name}: Начинаю парсинг HTML детальной информации для автомобиля {car_id}"
            )

            # Парсим HTML с помощью BeautifulSoup
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_content, "html.parser")

            # Создаем базовый объект с известными данными
            car = KCarDetailedCar(
                car_id=car_id,
                auction_code=auction_code,
                main_image=None,
                all_images=[],
                thumbnail_images=[],
                options=[],
            )

            # Пытаемся извлечь базовую информацию
            try:
                # 1. Ищем название автомобиля в таблице с классом "ttable_tit"
                car_name_row = soup.find("td", class_="ttable_tit", string="차명")
                if car_name_row:
                    car_name_cell = car_name_row.find_next_sibling("td")
                    if car_name_cell:
                        car.car_name = car_name_cell.get_text(strip=True)
                        logger.debug(f"🚗 Найдено название: {car.car_name}")
                    else:
                        logger.warning(f"⚠️ Не найдена ячейка с названием автомобиля для {car_id}")
                else:
                    logger.warning(f"⚠️ Не найден элемент <td class='ttable_tit'>차명</td> для {car_id}")

                # 2. Ищем номер автомобиля в таблице
                car_number_row = soup.find("td", class_="table_tit", string="차량번호")
                if car_number_row:
                    car_number_cell = car_number_row.find_next_sibling("td")
                    if car_number_cell:
                        car_number_p = car_number_cell.find("p")
                        if car_number_p:
                            car.car_number = car_number_p.get_text(strip=True)
                            logger.debug(f"🔢 Найден номер: {car.car_number}")

                # 3. Ищем год в таблице
                year_row = soup.find("td", class_="ttable_tit", string="연식")
                if year_row:
                    year_cell = year_row.find_next_sibling("td")
                    if year_cell:
                        car.year = year_cell.get_text(strip=True)
                        logger.debug(f"📅 Найден год: {car.year}")

                # 4. Ищем пробег в carinfo секции
                # Ищем элемент p, который содержит текст "주행거리"
                for p_tag in soup.find_all("p"):
                    if p_tag.get_text() and "주행거리" in p_tag.get_text():
                        mileage_span = p_tag.find("span")
                        if mileage_span:
                            car.mileage = mileage_span.get_text(strip=True)
                            logger.debug(f"🏃 Найден пробег: {car.mileage}")
                            break

                # 5. Ищем дату первой регистрации в carinfo секции
                # Ищем элемент p, который содержит текст "최초등록일"
                for p_tag in soup.find_all("p"):
                    if p_tag.get_text() and "최초등록일" in p_tag.get_text():
                        reg_date_span = p_tag.find("span")
                        if reg_date_span:
                            car.registration_date = reg_date_span.get_text(strip=True)
                            logger.debug(f"📅 Найдена дата регистрации: {car.registration_date}")
                            break

                # 6. Ищем топливо в carinfo секции
                fuel_p = soup.find("p", string=lambda text: text and "연료" in text)
                if fuel_p:
                    fuel_span = fuel_p.find("span")
                    if fuel_span:
                        car.fuel_type = fuel_span.get_text(strip=True)
                        logger.debug(f"⛽ Найдено топливо: {car.fuel_type}")

                # 7. Ищем коробку передач в таблице
                transmission_row = soup.find("td", class_="table_tit", string="미션")
                if transmission_row:
                    transmission_cell = transmission_row.find_next_sibling("td")
                    if transmission_cell:
                        transmission_p = transmission_cell.find("p")
                        if transmission_p:
                            car.transmission = transmission_p.get_text(strip=True)
                            logger.debug(f"⚙️ Найдена КПП: {car.transmission}")

                # 8. Ищем топливо и цвет в таблице
                fuel_color_row = soup.find("td", class_="table_tit", string="연료/색상")
                if fuel_color_row:
                    fuel_color_cell = fuel_color_row.find_next_sibling("td")
                    if fuel_color_cell:
                        fuel_color_p = fuel_color_cell.find("p")
                        if fuel_color_p:
                            fuel_color_text = fuel_color_p.get_text(strip=True)
                            if "/" in fuel_color_text:
                                fuel_part, color_part = fuel_color_text.split("/", 1)
                                if not car.fuel_type:  # Если еще не найдено
                                    car.fuel_type = fuel_part.strip()
                                car.exterior_color = color_part.strip()
                                logger.debug(
                                    f"🎨 Найдены топливо/цвет: {car.fuel_type}/{car.exterior_color}"
                                )

                # 9. Ищем главное изображение
                main_img = soup.find("img", id="main_img")
                if main_img and main_img.get("src"):
                    main_img_src = main_img.get("src")
                    if main_img_src.startswith("/"):
                        car.main_image = f"https://www.kcarauction.com{main_img_src}"
                    else:
                        car.main_image = main_img_src
                    logger.debug(f"📸 Найдено главное изображение: {car.main_image}")
                else:
                    logger.warning(f"⚠️ Не найдено главное изображение <img id='main_img'> для {car_id}")

                # 10. Ищем все изображения автомобиля (фильтруем элементы интерфейса)
                all_images = []
                img_tags = soup.find_all("img")

                for img in img_tags:
                    src = img.get("src", "")
                    if src:
                        # Формируем полный URL изображения
                        if src.startswith("http"):
                            full_url = src
                        elif src.startswith("/"):
                            full_url = f"https://www.kcarauction.com{src}"
                        else:
                            full_url = f"https://www.kcarauction.com/{src}"

                        # Фильтруем только фотографии автомобиля
                        # Исключаем элементы интерфейса, логотипы и иконки
                        full_url_lower = full_url.lower()

                        # Фотографии автомобиля должны содержать ID автомобиля и находиться в папке IMAGE_UPLOAD/CAR
                        if (
                            car_id.lower() in full_url_lower
                            and "/image_upload/car/" in full_url_lower
                        ):
                            if full_url not in all_images:
                                all_images.append(full_url)
                        # Или быть главным изображением (main_img)
                        elif (
                            img.get("id") == "main_img"
                            and car_id.lower() in full_url_lower
                        ):
                            if full_url not in all_images:
                                all_images.append(full_url)

                car.all_images = all_images
                logger.debug(f"📸 Найдено {len(all_images)} изображений")

                # 10. Ищем VIN номер
                vin_row = soup.find("td", class_="ttable_tit", string="차대번호")
                if vin_row:
                    vin_cell = vin_row.find_next_sibling("td")
                    if vin_cell:
                        car.vin = vin_cell.get_text(strip=True)
                        logger.debug(f"🔐 Найден VIN: {car.vin}")

                # 11. Ищем объем двигателя
                displacement_row = soup.find("td", class_="table_tit", string="배기량")
                if displacement_row:
                    displacement_cell = displacement_row.find_next_sibling("td")
                    if displacement_cell:
                        displacement_p = displacement_cell.find("p")
                        if displacement_p:
                            car.displacement = displacement_p.get_text(strip=True)
                            logger.debug(
                                f"🔧 Найден объем двигателя: {car.displacement}"
                            )

                # 12. Извлекаем стартовую цену
                start_price_elem = soup.find("strong", {"id": "auc_strt_prc"})
                if start_price_elem:
                    car.start_price = start_price_elem.get_text(strip=True)
                    logger.debug(f"💰 Найдена стартовая цена: {car.start_price}만원")
                else:
                    logger.warning(f"⚠️ Не найдена стартовая цена <strong id='auc_strt_prc'> для {car_id}")

                # 13. Извлекаем ожидаемую цену (если есть)
                expected_price_elem = soup.find("strong", {"id": "auc_strt_hope"})
                if expected_price_elem:
                    car.expected_price = expected_price_elem.get_text(strip=True)
                    logger.debug(f"💰 Найдена ожидаемая цена: {car.expected_price}만원")

                # 14. Извлекаем дату аукциона
                auction_date_elem = soup.find("strong", {"id": "auc_strt_dt"})
                if auction_date_elem:
                    car.auction_date = auction_date_elem.get_text(strip=True)
                    logger.debug(f"📅 Найдена дата аукциона: {car.auction_date}")

                # 15. Извлекаем статус аукциона
                auction_status_elem = soup.find("strong", {"id": "auc_stat"})
                if auction_status_elem:
                    car.auction_status = auction_status_elem.get_text(strip=True)
                    logger.debug(f"📊 Найден статус аукциона: {car.auction_status}")

                logger.debug(
                    f"🔍 Извлеченные данные: название={car.car_name}, номер={car.car_number}, год={car.year}, пробег={car.mileage}, цена={car.start_price}"
                )
                
                # 16. Пытаемся извлечь технический лист
                try:
                    technical_sheet = self._parse_technical_sheet(soup)
                    if technical_sheet:
                        car.technical_sheet = technical_sheet
                        logger.debug(f"📋 Найден технический лист с инспекциями")
                except Exception as tech_error:
                    logger.warning(f"⚠️ Ошибка извлечения технического листа: {tech_error}")

            except Exception as parse_error:
                logger.warning(f"⚠️ Ошибка извлечения данных из HTML: {parse_error}")

            # Валидация: проверяем, были ли извлечены критические данные
            has_critical_data = bool(car.car_name or car.main_image or car.start_price)

            if not has_critical_data:
                logger.error(
                    f"❌ {self.name}: Критические данные не извлечены для {car_id}. "
                    f"car_name={car.car_name}, main_image={car.main_image}, start_price={car.start_price}"
                )

                # Сохраняем HTML для отладки
                try:
                    import os
                    from datetime import datetime

                    # Создаем директорию для отладочных файлов
                    debug_dir = "debug_html"
                    os.makedirs(debug_dir, exist_ok=True)

                    # Сохраняем HTML с временной меткой
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    debug_filename = f"{debug_dir}/kcar_empty_detail_{car_id}_{timestamp}.html"

                    with open(debug_filename, "w", encoding="utf-8") as f:
                        f.write(html_content)

                    logger.info(f"💾 HTML сохранен для отладки: {debug_filename}")
                except Exception as save_error:
                    logger.warning(f"⚠️ Не удалось сохранить HTML для отладки: {save_error}")

            response = KCarDetailResponse(
                car=car,
                success=has_critical_data,  # Успех только если данные извлечены
                message="Детальная информация получена успешно" if has_critical_data else "Не удалось извлечь критические данные из HTML. Возможно, автомобиль более недоступен или был удален с аукциона.",
                source_url=f"https://www.kcarauction.com/kcar/auction/weekly_detail/auction_detail_view.do?CAR_ID={car_id}&AUC_CD={auction_code}",
                error_type=None if has_critical_data else "car_not_found",
            )

            if has_critical_data:
                logger.success(
                    f"✅ {self.name}: Детальная информация для автомобиля {car_id} обработана успешно"
                )
            else:
                logger.warning(
                    f"⚠️ {self.name}: Детальная информация для автомобиля {car_id} обработана, но критические данные не найдены"
                )

            return response

        except Exception as e:
            logger.error(
                f"❌ {self.name}: Ошибка парсинга детальной информации для автомобиля {car_id}: {e}"
            )
            return KCarDetailResponse(
                car=None,
                success=False,
                message=f"Ошибка парсинга детальной информации: {str(e)}",
                error_type="parsing_failed",
            )

    def _parse_technical_sheet(self, soup) -> Optional[TechnicalSheet]:
        """
        Извлечение данных технического листа из HTML
        
        Args:
            soup: BeautifulSoup объект страницы
            
        Returns:
            TechnicalSheet объект или None
        """
        try:
            # Ищем секцию с техническим листом
            tech_sheet_div = soup.find("div", class_="optiontest")
            if not tech_sheet_div:
                logger.debug("Секция технического листа не найдена")
                return None
                
            tech_sheet = TechnicalSheet()
            
            # 1. Извлекаем номер инспекции
            inspection_p = tech_sheet_div.find("p", string=lambda x: x and "제" in x and "호" in x)
            if inspection_p:
                tech_sheet.inspection_number = inspection_p.get_text(strip=True)
                
            # 2. Извлекаем номер формы
            form_p = tech_sheet_div.find("p", string=lambda x: x and "별지" in x)
            if form_p:
                tech_sheet.form_number = form_p.get_text(strip=True)
                
            # 3. Извлекаем информацию о владельце
            owner_info = {}
            owner_company_cell = soup.find("td", string="상호(명칭)")
            if owner_company_cell:
                owner_company_value = owner_company_cell.find_next_sibling("td")
                if owner_company_value:
                    owner_info["company"] = owner_company_value.get_text(strip=True)
                    
            owner_name_cell = soup.find("td", string="성명(대표자)")
            if owner_name_cell:
                owner_name_value = owner_name_cell.find_next_sibling("td")
                if owner_name_value:
                    owner_info["name"] = owner_name_value.get_text(strip=True)
                    
            owner_id_cell = soup.find("td", string="주민등록번호")
            if owner_id_cell:
                owner_id_value = owner_id_cell.find_next_sibling("td")
                if owner_id_value:
                    owner_info["id"] = owner_id_value.get_text(strip=True)
                    
            if owner_info:
                tech_sheet.owner_info = owner_info
                
            # 4. Извлекаем состояние VIN
            vin_conditions = []
            vin_checkboxes = soup.find_all("input", {"id": lambda x: x and x.startswith("SAMENESS_")})
            for checkbox in vin_checkboxes:
                if checkbox.get("checked") is not None:
                    label = checkbox.find_next_sibling("label")
                    if label:
                        vin_conditions.append(label.get_text(strip=True))
            
            if vin_conditions:
                tech_sheet.vin_condition = vin_conditions
                
            # 5. Проверка регистрации
            reg_confirmed_cell = soup.find("td", string="등록사항 확인")
            if reg_confirmed_cell:
                reg_value_cell = reg_confirmed_cell.find_next_sibling("td")
                if reg_value_cell:
                    reg_value = reg_value_cell.get_text(strip=True).upper()
                    tech_sheet.registration_confirmed = reg_value == "Y"
                    
            # 6. Извлекаем результаты инспекций систем
            inspection_mappings = {
                "10.기관장치": "engine_system",
                "11.동력전달장치": "power_transmission", 
                "12.제동장치": "braking_system",
                "13.조향장치": "steering_system",
                "14.등화장치": "lighting_system",
                "15.주행장치": "running_gear",
                "17.축전기계장치": "battery_system"
            }
            
            for korean_name, field_name in inspection_mappings.items():
                inspection_cell = soup.find("td", string=korean_name)
                if inspection_cell:
                    result_cell = inspection_cell.find_next_sibling("td")
                    if result_cell:
                        status_text = result_cell.get_text(strip=True)
                        inspection = TechnicalSheetInspection(status=status_text)
                        
                        # Определяем код статуса
                        if status_text == "양호":
                            inspection.status_code = "V"
                        elif status_text == "불량":
                            inspection.status_code = "O"
                        elif status_text == "수리":
                            inspection.status_code = "△"
                            
                        setattr(tech_sheet, field_name, inspection)
                        
            # 7. Извлекаем детальные инспекции компонентов
            detailed_inspections = {}
            checkbox_sections = tech_sheet_div.find_all("div", class_="check_rd20w")
            
            current_section = None
            for checkbox_div in checkbox_sections:
                checkbox = checkbox_div.find("input", type="checkbox")
                if checkbox:
                    name = checkbox.get("name", "")
                    if name and name.startswith("i_arr"):
                        section_name = name.replace("i_arr", "").lower()
                        if checkbox.get("checked") is not None:
                            label = checkbox_div.find("label")
                            if label:
                                if section_name not in detailed_inspections:
                                    detailed_inspections[section_name] = []
                                detailed_inspections[section_name].append(label.get_text(strip=True))
                                
            if detailed_inspections:
                tech_sheet.detailed_inspections = detailed_inspections
                
            # 8. Извлекаем состояние частей кузова
            body_parts = {
                "replaced": [],
                "panel_beaten": [],
                "corroded": [],
                "adjusted": []
            }
            
            # Словарь для отслеживания типа повреждения по номеру части
            damage_type_by_part = {}
            
            # Ищем активные элементы на схеме кузова
            # В HTML активные части отмечены классом "on"
            active_parts = soup.find_all("li", class_="on")
            for part in active_parts:
                part_id = part.get("id", "")
                if part_id and len(part_id) >= 6:  # e.g., aw0107
                    # Извлекаем номер части (последние 4 цифры)
                    part_number = part_id[-4:]
                    
                    # Определяем тип работы по префиксу
                    if part_id.startswith("aw"):  # 판금 (panel beating) - W
                        body_parts["panel_beaten"].append(part_number)
                        damage_type_by_part[part_number] = "panel_beaten"
                    elif part_id.startswith("ax"):  # 교환 (replacement) - X
                        body_parts["replaced"].append(part_number)
                        damage_type_by_part[part_number] = "replaced"
                    elif part_id.startswith("ac"):  # 부식 (corrosion)
                        body_parts["corroded"].append(part_number)
                        damage_type_by_part[part_number] = "corroded"
                    elif part_id.startswith("aa"):  # 조정 (adjustment)
                        body_parts["adjusted"].append(part_number)
                        damage_type_by_part[part_number] = "adjusted"
                    elif part_id.startswith("az"):  # 전면유리 (front glass) - treated as replacement
                        body_parts["replaced"].append(part_number)
                        damage_type_by_part[part_number] = "replaced"
                        
            # Также проверяем активные области на карте
            # Area элементы соответствуют тем же частям, что и li элементы
            active_areas = soup.find_all("area", class_="on")
            for area in active_areas:
                area_id = area.get("id", "")
                if area_id and area_id.startswith("p") and len(area_id) == 5:  # e.g., p0107
                    # Извлекаем номер части
                    part_number = area_id[1:]  # Remove 'p' prefix
                    
                    # Если эта часть уже обработана через li элемент, пропускаем
                    if part_number not in damage_type_by_part:
                        # Если нет соответствующего li элемента, добавляем как adjusted по умолчанию
                        body_parts["adjusted"].append(part_number)
                        damage_type_by_part[part_number] = "adjusted"
                    
            if any(body_parts.values()):
                tech_sheet.body_parts = body_parts
                
            # 9. Извлекаем дополнительные замечания
            special_notes = soup.find("td", string=lambda x: x and "특이사항" in x if x else False)
            if special_notes:
                notes_cell = special_notes.find_next_sibling("td") 
                if notes_cell:
                    tech_sheet.additional_notes = notes_cell.get_text(strip=True)
                    
            return tech_sheet
            
        except Exception as e:
            logger.error(f"Ошибка парсинга технического листа: {e}")
            return None

    def parse_models_json(self, json_data: Dict[str, Any]) -> KCarModelsResponse:
        """
        Парсинг JSON ответа со списком моделей

        Args:
            json_data: JSON данные от KCar API моделей

        Returns:
            KCarModelsResponse с списком моделей
        """
        try:
            logger.info(f"📊 {self.name}: Начинаю парсинг JSON моделей")

            # Создаем ответ напрямую из JSON данных
            # Pydantic автоматически обработает алиасы полей
            response = KCarModelsResponse.model_validate(json_data)
            response.success = True
            response.message = f"Успешно получено {len(response.models)} моделей"

            logger.success(
                f"✅ {self.name}: Успешно обработано {len(response.models)} моделей"
            )
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка парсинга JSON моделей: {e}")
            logger.debug(f"🔍 JSON данные: {json_data}")
            return KCarModelsResponse(
                models=[],
                success=False,
                message=f"Ошибка парсинга моделей: {str(e)}",
            )

    def parse_generations_json(
        self, json_data: Dict[str, Any]
    ) -> KCarGenerationsResponse:
        """
        Парсинг JSON ответа со списком поколений

        Args:
            json_data: JSON данные от KCar API поколений

        Returns:
            KCarGenerationsResponse с списком поколений
        """
        try:
            logger.info(f"📊 {self.name}: Начинаю парсинг JSON поколений")

            # Создаем ответ напрямую из JSON данных
            # Pydantic автоматически обработает алиасы полей
            response = KCarGenerationsResponse.model_validate(json_data)
            response.success = True
            response.message = f"Успешно получено {len(response.generations)} поколений"

            logger.success(
                f"✅ {self.name}: Успешно обработано {len(response.generations)} поколений"
            )
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка парсинга JSON поколений: {e}")
            logger.debug(f"🔍 JSON данные: {json_data}")
            return KCarGenerationsResponse(
                generations=[],
                success=False,
                message=f"Ошибка парсинга поколений: {str(e)}",
            )

    def parse_search_json(self, json_data: Dict[str, Any]) -> KCarSearchResponse:
        """
        Парсинг JSON ответа расширенного поиска

        Args:
            json_data: JSON данные от KCar API поиска

        Returns:
            KCarSearchResponse с результатами поиска
        """
        try:
            logger.info(f"📊 {self.name}: Начинаю парсинг JSON результатов поиска")

            cars = []
            car_list = json_data.get("CAR_LIST", [])

            logger.info(f"📋 Найдено {len(car_list)} автомобилей в результатах поиска")

            # Парсим каждый автомобиль
            for car_data in car_list:
                try:
                    car = self._parse_single_car(car_data)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга автомобиля в поиске: {e}")
                    continue

            # Извлекаем параметры запроса
            request_params = json_data.get("auctionReqVo", {})

            # Извлекаем информацию о пагинации
            current_page = request_params.get("START_RNUM", 1)
            page_size = request_params.get("PAGE_CNT", 18)

            # Рассчитываем общее количество страниц
            total_pages = None
            if len(cars) == page_size:
                # Если получили полную страницу, скорее всего есть еще
                total_pages = current_page + 1
            else:
                # Если получили неполную страницу, это последняя страница
                total_pages = current_page

            response = KCarSearchResponse(
                request_params=request_params,
                cars=cars,
                total_count=len(cars),
                current_page=current_page,
                page_size=page_size,
                total_pages=total_pages,
                success=True,
                message=f"Найдено {len(cars)} автомобилей",
            )

            logger.success(
                f"✅ {self.name}: Успешно обработан поиск - найдено {len(cars)} автомобилей"
            )
            return response

        except Exception as e:
            logger.error(
                f"❌ {self.name}: Ошибка парсинга JSON результатов поиска: {e}"
            )
            return KCarSearchResponse(
                cars=[],
                total_count=0,
                current_page=1,
                page_size=18,
                success=False,
                message=f"Ошибка парсинга результатов поиска: {str(e)}",
            )
