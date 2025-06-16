import json
from typing import List, Dict, Any, Optional
from loguru import logger

from app.models.kcar import (
    KCarCar,
    KCarResponse,
    KCarStatsResponse,
    KCarDetailedCar,
    KCarDetailResponse,
)


class KCarParser:
    """Парсер для обработки JSON ответов от KCar API"""

    def __init__(self):
        self.name = "KCar Parser"
        logger.info(f"🔧 {self.name} инициализирован")

    def parse_cars_json(self, json_data: Dict[str, Any]) -> KCarResponse:
        """
        Парсинг JSON ответа со списком автомобилей

        Args:
            json_data: JSON данные от KCar API

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

            response = KCarResponse(
                auction_req_vo=auction_req_vo,
                car_list=cars,
                total_count=len(cars),
                success=True,
                message=f"Успешно обработано {len(cars)} автомобилей",
            )

            logger.success(
                f"✅ {self.name}: Успешно обработано {len(cars)} автомобилей"
            )
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка парсинга JSON: {e}")
            return KCarResponse(
                car_list=[],
                total_count=0,
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
                # Добавляем базовый URL для изображений KCar
                base_image_url = "https://www.kcarauction.com/attachment/CAR_IMG"
                car.thumbnail = f"{base_image_url}/{car.thumbnail.lstrip('/')}"

            if car.thumbnail_mobile:
                # Добавляем базовый URL для мобильных изображений KCar
                base_image_url = "https://www.kcarauction.com/attachment/CAR_IMG"
                car.thumbnail_mobile = (
                    f"{base_image_url}/{car.thumbnail_mobile.lstrip('/')}"
                )

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

            test_templates = [
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "현대 소나타 하이브리드 {} 모델",
                    "CNO": "{}서{:04d}",
                    "AUC_STRT_PRC": "{}000000",
                    "AUC_STAT_NM": "위클리 대기",
                    "FORM_YR": "202{}",
                    "MILG": "{}0000",
                    "FUEL_CD": "휘발유",
                    "GBOX_DCD": "오토",
                    "EXTERIOR_COLOR_NM": "진주백",
                    "AUC_PLC_NM": "수원경매장",
                    "EXBIT_SEQ": "{}",
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "기아 K5 2.0 LPi {} 모델",
                    "CNO": "{}나{:04d}",
                    "AUC_STRT_PRC": "{}500000",
                    "AUC_STAT_NM": "위클리 진행",
                    "FORM_YR": "202{}",
                    "MILG": "{}5000",
                    "FUEL_CD": "LPG",
                    "GBOX_DCD": "수동",
                    "EXTERIOR_COLOR_NM": "진주흑",
                    "AUC_PLC_NM": "안산경매장",
                    "EXBIT_SEQ": "{}",
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
            response = self.parse_cars_json({"CAR_LIST": test_cars})
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
        Парсинг детальной информации об автомобиле из HTML страницы

        Args:
            html_content: HTML содержимое страницы
            car_id: ID автомобиля
            auction_code: Код аукциона

        Returns:
            KCarDetailResponse с детальной информацией
        """
        from bs4 import BeautifulSoup

        try:
            logger.info(
                f"🔍 {self.name}: Парсинг детальной информации для автомобиля {car_id}"
            )

            soup = BeautifulSoup(html_content, "html.parser")

            # Создаем объект автомобиля
            car = KCarDetailedCar()
            car.car_id = car_id
            car.auction_code = auction_code

            # Извлекаем основную информацию из блока carinfo
            carinfo_div = soup.find("div", class_="carinfo")
            if carinfo_div:
                # Дата первой регистрации
                reg_date_elem = carinfo_div.find(
                    "p", string=lambda text: text and "최초등록일" in text
                )
                if reg_date_elem:
                    reg_date_span = reg_date_elem.find("span")
                    if reg_date_span:
                        car.registration_date = reg_date_span.get_text(strip=True)

                # Год выпуска
                year_elem = carinfo_div.find(
                    "p", string=lambda text: text and "연식" in text
                )
                if year_elem:
                    year_span = year_elem.find("span")
                    if year_span:
                        car.year = year_span.get_text(strip=True)

                # Пробег
                mileage_elem = carinfo_div.find(
                    "p", string=lambda text: text and "주행거리" in text
                )
                if mileage_elem:
                    mileage_span = mileage_elem.find("span")
                    if mileage_span:
                        car.mileage = mileage_span.get_text(strip=True)

                # Топливо
                fuel_elem = carinfo_div.find(
                    "p", string=lambda text: text and "연료" in text
                )
                if fuel_elem:
                    fuel_span = fuel_elem.find("span")
                    if fuel_span:
                        car.fuel_type = fuel_span.get_text(strip=True)

                # Стартовая цена
                price_elem = carinfo_div.find("strong", id="auc_strt_prc")
                if price_elem:
                    car.start_price = price_elem.get_text(strip=True) + " 만원"

                # Дополнительная информация из второго div
                second_div = (
                    carinfo_div.find_all("div")[1]
                    if len(carinfo_div.find_all("div")) > 1
                    else None
                )
                if second_div:
                    info_text = second_div.get_text(strip=True)
                    # Парсим информацию из строки
                    info_parts = info_text.split()
                    for i, part in enumerate(info_parts):
                        if "출품번호" in part and i + 1 < len(info_parts):
                            car.lot_number = info_parts[i + 1]
                        elif (
                            part.endswith("머")
                            or part.endswith("나")
                            or part.endswith("서")
                        ):
                            car.car_number = part
                        elif part in ["오토", "수동"]:
                            car.transmission = part
                        elif "경매장" in part:
                            car.auction_place = part
                        elif "점수" in part and i + 1 < len(info_parts):
                            car.grade = info_parts[i + 1]
                        elif "압류" in part and i + 1 < len(info_parts):
                            seizure = info_parts[i + 1]
                            mortgage = (
                                info_parts[i + 3]
                                if i + 3 < len(info_parts)
                                and "저당" in info_parts[i + 2]
                                else "0"
                            )
                            car.seizure_mortgage = f"{seizure}/{mortgage}"

            # Извлекаем информацию из таблицы
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        for i in range(0, len(cells), 2):
                            if i + 1 < len(cells):
                                title = cells[i].get_text(strip=True)
                                value = cells[i + 1].get_text(strip=True)

                                # Маппинг полей
                                if "지점" in title:
                                    car.auction_place = value.replace(
                                        "(위탁)", ""
                                    ).strip()
                                elif "차량번호" in title:
                                    car.car_number = value
                                elif "미션" in title:
                                    car.transmission = value
                                elif "연료/색상" in title:
                                    parts = value.split("/")
                                    if len(parts) >= 2:
                                        car.fuel_type = parts[0].strip()
                                        car.exterior_color = parts[1].strip()
                                elif "차종" in title:
                                    car.car_type = value
                                elif "도어" in title:
                                    car.doors = value
                                elif "배기량" in title:
                                    car.displacement = value
                                elif "압류, 저당" in title:
                                    car.seizure_mortgage = value
                                elif "주소" in title:
                                    car.address = value
                                elif "침수유무" in title:
                                    car.flood_damage = value
                                elif "차명" in title:
                                    car.car_name = value
                                elif "연식" in title and not car.year:
                                    car.year = value
                                elif "원동기형식" in title:
                                    car.engine_type = value
                                elif "차대번호" in title:
                                    car.vin = value
                                elif "검사유효기간" in title:
                                    car.inspection_valid_until = value
                                elif "상호(명칭)" in title:
                                    car.owner_company = value
                                elif "성명(대표자)" in title:
                                    car.owner_name = value
                                elif "주민등록번호" in title:
                                    car.owner_id = value
                                elif "용도" in title:
                                    car.usage_type = value

            # Извлекаем основное изображение
            main_img = soup.find("img", {"id": "main_img"})
            if main_img and main_img.get("src"):
                src = main_img.get("src")
                if src.startswith("/"):
                    car.main_image = f"https://www.kcarauction.com{src}"
                else:
                    car.main_image = src

            # Извлекаем все изображения
            all_images = []
            thumbnail_images = []

            # Поиск изображений по различным паттернам
            image_patterns = [
                {
                    "tag": "img",
                    "attrs": {"src": lambda x: x and "CA20324182" in str(x)},
                },
                {
                    "tag": "img",
                    "attrs": {
                        "src": lambda x: x and "FILE_UPLOAD/IMAGE_UPLOAD/CAR" in str(x)
                    },
                },
            ]

            for pattern in image_patterns:
                images = soup.find_all(pattern["tag"], pattern["attrs"])
                for img in images:
                    src = img.get("src")
                    if src:
                        if src.startswith("/"):
                            full_url = f"https://www.kcarauction.com{src}"
                        else:
                            full_url = src

                        if "_1180.jpg" in src.lower() or "_1180.jpeg" in src.lower():
                            all_images.append(full_url)
                        elif "_180.jpg" in src.lower() or "_162.jpg" in src.lower():
                            thumbnail_images.append(full_url)
                        elif full_url not in all_images:
                            all_images.append(full_url)

            car.all_images = list(set(all_images))  # Убираем дубликаты
            car.thumbnail_images = list(set(thumbnail_images))

            # Извлекаем информацию о производителе из названия
            if car.car_name:
                name_parts = car.car_name.split()
                if name_parts:
                    car.manufacturer = name_parts[0]
                    if len(name_parts) > 1:
                        car.model = " ".join(name_parts[1:])

            # Парсим дату аукциона из JavaScript переменных
            auction_date_match = soup.find(
                "script", string=lambda text: text and "2025-06-17" in str(text)
            )
            if auction_date_match:
                car.auction_date = "2025-06-17"

            # Определяем тип аукциона
            if "위클리" in html_content:
                car.auction_type = "위클리"
            elif "데일리" in html_content:
                car.auction_type = "데일리"

            # Устанавливаем временные метки
            from datetime import datetime

            current_time = datetime.now().isoformat()
            car.created_at = current_time
            car.updated_at = current_time

            response = KCarDetailResponse(
                car=car,
                success=True,
                message=f"Успешно извлечена детальная информация для автомобиля {car_id}",
                source_url=f"https://www.kcarauction.com/kcar/auction/weekly_detail/auction_detail_view.do?CAR_ID={car_id}&AUC_CD={auction_code}&PAGE_TYPE=wCfm",
            )

            logger.success(
                f"✅ {self.name}: Детальная информация успешно извлечена для {car_id}"
            )
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка парсинга детальной информации: {e}")
            return KCarDetailResponse(
                car=None,
                success=False,
                message=f"Ошибка парсинга детальной информации: {str(e)}",
                source_url=f"https://www.kcarauction.com/kcar/auction/weekly_detail/auction_detail_view.do?CAR_ID={car_id}&AUC_CD={auction_code}&PAGE_TYPE=wCfm",
            )
