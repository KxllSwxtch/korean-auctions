import json
from typing import List, Dict, Any, Optional
from loguru import logger

from app.models.kcar import KCarCar, KCarResponse, KCarStatsResponse


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

            # Логируем основную информацию об автомобиле
            car_info = (
                f"ID: {car.car_id}, Название: {car.car_name}, Номер: {car.car_number}"
            )
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
                # Подсчет типов аукционов
                if car.auction_type_desc and "DAILY" in car.auction_type_desc.upper():
                    daily_auctions += 1
                elif (
                    car.auction_type_desc and "WEEKLY" in car.auction_type_desc.upper()
                ):
                    weekly_auctions += 1

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
                    "AUC_STAT_NM": "데일리 시작",
                    "FORM_YR": "{}",
                    "EXTERIOR_COLOR_NM": "진주색",
                    "CAR_LOCT": "서울경매장",
                    "AUC_TYPE_DESC": "DAILY",
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "기아 K5 {} 모델",
                    "CNO": "{}부{:04d}",
                    "AUC_STRT_PRC": "{}500000",
                    "AUC_STAT_NM": "위클리 대기",
                    "FORM_YR": "{}",
                    "EXTERIOR_COLOR_NM": "검정색",
                    "CAR_LOCT": "부산경매장",
                    "AUC_TYPE_DESC": "WEEKLY",
                },
                {
                    "CAR_ID": "KCA2025{:04d}",
                    "CAR_NM": "삼성르노 QM6 {} 모델",
                    "CNO": "{}경{:04d}",
                    "AUC_STRT_PRC": "{}200000",
                    "AUC_STAT_NM": "데일리 진행중",
                    "FORM_YR": "{}",
                    "EXTERIOR_COLOR_NM": "흰색",
                    "CAR_LOCT": "경기경매장",
                    "AUC_TYPE_DESC": "DAILY",
                },
            ]

            for i in range(count):
                template = test_templates[i % len(test_templates)]

                car_data = {}
                for key, value_template in template.items():
                    if "{}" in str(value_template):
                        if key == "CAR_ID":
                            car_data[key] = value_template.format(i + 1)
                        elif key == "CAR_NM":
                            car_data[key] = value_template.format(2020 + (i % 5))
                        elif key == "CNO":
                            regions = ["12", "23", "34", "45", "56"]
                            car_data[key] = value_template.format(
                                regions[i % len(regions)], i + 1000
                            )
                        elif key == "AUC_STRT_PRC":
                            prices = ["15", "18", "22", "25", "30"]
                            car_data[key] = value_template.format(
                                prices[i % len(prices)]
                            )
                        elif key == "FORM_YR":
                            car_data[key] = str(2018 + (i % 7))
                    else:
                        car_data[key] = value_template

                # Добавляем дополнительные поля
                car_data.update(
                    {
                        "AUC_CD": f"KCA{2025}{(i % 12) + 1:02d}{(i % 30) + 1:02d}",
                        "EXBIT_SEQ": str(1000 + i),
                        "CAR_POINT": str((i % 5) + 3),
                        "CAR_POINT2": chr(65 + (i % 5)),  # A, B, C, D, E
                        "MILG": str((i + 1) * 10000 + (i % 10) * 1000),
                        "FUEL_CD": "G" if i % 2 == 0 else "D",
                        "GBOX_DCD": "A" if i % 3 == 0 else "M",
                        "CAR_USE_NM": "자가" if i % 4 == 0 else "영업용",
                        "ACCIDENT_YN": "N" if i % 5 != 0 else "Y",
                    }
                )

                car = KCarCar(**car_data)
                test_cars.append(car)

            response = KCarResponse(
                car_list=test_cars,
                total_count=count,
                success=True,
                message=f"Сгенерировано {count} тестовых автомобилей KCar",
            )

            logger.success(
                f"✅ {self.name}: Сгенерировано {count} тестовых автомобилей"
            )
            return response

        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка генерации тестовых данных: {e}")
            return KCarResponse(
                car_list=[],
                total_count=0,
                success=False,
                message=f"Ошибка генерации тестовых данных: {str(e)}",
            )
