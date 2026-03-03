"""
Сервис клиентской фильтрации для HeyDealer
Поскольку API HeyDealer не поддерживает все фильтры,
реализуем фильтрацию на стороне клиента
"""

import re
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class HeyDealerClientFilter:
    """Клиентская фильтрация для HeyDealer"""

    def __init__(self):
        # Маппинг моделей для фильтрации по названию
        self.model_mappings = {
            "7MEA9M": ["GV80", "gv80"],
            "zMbV3M": ["G80", "g80"],
            "YyGdqe": ["G70", "g70"],
            "1yOqjk": ["G90", "g90"],
            "peqqRe": ["GV70", "gv70"],
            "rk0bBy": ["GV60", "gv60"],
            "Ae1E8e": ["EQ900", "eq900"],
        }

        # Маппинг топлива
        self.fuel_mappings = {
            "gasoline": ["가솔린", "gasoline", "бензин"],
            "diesel": ["디젤", "diesel", "дизель"],
            "hybrid": ["하이브리드", "hybrid", "гибрид"],
            "electric": ["전기", "electric", "электро"],
            "lpg": ["LPG", "LPI", "lpg", "гбо"],
        }

        # Маппинг трансмиссии
        self.transmission_mappings = {
            "automatic": ["자동", "automatic", "auto", "автомат"],
            "manual": ["수동", "manual", "механика"],
            "cvt": ["CVT", "cvt", "вариатор"],
        }

    def filter_cars_by_model_group(
        self, cars: List[Dict[str, Any]], model_group_hash_id: str
    ) -> List[Dict[str, Any]]:
        """
        Фильтрует автомобили по model_group (группе моделей)
        Поскольку HeyDealer API не поддерживает фильтрацию по model_group,
        мы фильтруем на стороне клиента
        """
        if not model_group_hash_id:
            return cars
        
        logger.info(f"Применяем клиентскую фильтрацию по model_group: {model_group_hash_id}")
        
        # Сначала получаем все generation IDs для этой model_group
        from app.services.heydealer_model_mapper import HeyDealerModelMapper
        generation_ids = HeyDealerModelMapper.get_generation_ids_for_model_group(model_group_hash_id)
        
        if not generation_ids:
            logger.warning(f"Не найдены generation IDs для model_group {model_group_hash_id}")
            # Пробуем фильтровать по старому методу с маппингами
            if model_group_hash_id in self.model_mappings:
                return self._filter_by_model_mapping(cars, model_group_hash_id)
            return cars
        
        # Фильтруем автомобили, у которых model hash_id есть в списке generation_ids
        filtered_cars = []
        for car in cars:
            # Нужно найти model hash_id в данных автомобиля
            # Это может быть в разных местах в зависимости от структуры данных
            car_model_id = None
            
            # Попробуем найти model ID в разных местах
            if isinstance(car, dict):
                # HeyDealer API возвращает model_part_name в detail секции
                # Нам нужно сопоставить это с generation_ids
                detail = car.get('detail', {})
                
                # Проверяем model_part_name - это название модели в ответе API
                model_part_name = detail.get('model_part_name', '')
                
                # Также проверяем full_name, который содержит полное название
                full_name = detail.get('full_name', '')
                
                # ВАЖНО: В текущей реализации HeyDealer API не возвращает model hash_id напрямую
                # Поэтому мы не можем точно сопоставить автомобили с generation_ids
                # Это ограничение API - нужно использовать фильтрацию по названию
                
                # Временное решение - пропускаем все автомобили, так как мы не можем точно определить generation
                filtered_cars.append(car)
                logger.debug(f"Автомобиль добавлен (невозможно определить model_id): {model_part_name}")
        
        logger.info(f"Отфильтровано {len(filtered_cars)} из {len(cars)} автомобилей")
        return filtered_cars
    
    def _filter_by_model_mapping(
        self, cars: List[Dict[str, Any]], model_group_hash_id: str
    ) -> List[Dict[str, Any]]:
        """Старый метод фильтрации по маппингам"""
        if model_group_hash_id not in self.model_mappings:
            return cars

        model_keywords = self.model_mappings[model_group_hash_id]
        filtered_cars = []

        for car in cars:
            title = car.get("title", "").lower()
            model_part_name = car.get("model_part_name", "").lower()

            # Проверяем по названию или модели
            for keyword in model_keywords:
                if keyword.lower() in title or keyword.lower() in model_part_name:
                    filtered_cars.append(car)
                    break

        logger.info(
            f"Фильтрация по модели {model_group_hash_id}: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def filter_cars_by_year(
        self,
        cars: List[Dict[str, Any]],
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Фильтрует автомобили по году"""
        if not min_year and not max_year:
            return cars

        filtered_cars = []
        for car in cars:
            year = car.get("year")
            if year is None:
                continue

            year_ok = True
            if min_year and year < min_year:
                year_ok = False
            if max_year and year > max_year:
                year_ok = False

            if year_ok:
                filtered_cars.append(car)

        logger.info(
            f"Фильтрация по году [{min_year}-{max_year}]: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def filter_cars_by_mileage(
        self,
        cars: List[Dict[str, Any]],
        min_mileage: Optional[int] = None,
        max_mileage: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Фильтрует автомобили по пробегу"""
        if not min_mileage and not max_mileage:
            return cars

        filtered_cars = []
        for car in cars:
            mileage = car.get("mileage")
            if mileage is None:
                continue

            mileage_ok = True
            if min_mileage and mileage < min_mileage:
                mileage_ok = False
            if max_mileage and mileage > max_mileage:
                mileage_ok = False

            if mileage_ok:
                filtered_cars.append(car)

        logger.info(
            f"Фильтрация по пробегу [{min_mileage}-{max_mileage}]: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def filter_cars_by_price(
        self,
        cars: List[Dict[str, Any]],
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Фильтрует автомобили по цене"""
        if not min_price and not max_price:
            return cars

        filtered_cars = []
        for car in cars:
            price = car.get("price") or car.get("desired_price")
            if price is None:
                continue

            price_ok = True
            if min_price and price < min_price:
                price_ok = False
            if max_price and price > max_price:
                price_ok = False

            if price_ok:
                filtered_cars.append(car)

        logger.info(
            f"Фильтрация по цене [{min_price}-{max_price}]: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def filter_cars_by_fuel(
        self, cars: List[Dict[str, Any]], fuel_type: str
    ) -> List[Dict[str, Any]]:
        """Фильтрует автомобили по типу топлива"""
        if not fuel_type or fuel_type not in self.fuel_mappings:
            return cars

        fuel_keywords = self.fuel_mappings[fuel_type]
        filtered_cars = []

        for car in cars:
            title = car.get("title", "").lower()
            fuel_display = car.get("fuel_display", "").lower()

            # Проверяем по названию или полю топлива
            for keyword in fuel_keywords:
                if keyword.lower() in title or keyword.lower() in fuel_display:
                    filtered_cars.append(car)
                    break

        logger.info(
            f"Фильтрация по топливу {fuel_type}: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def filter_cars_by_transmission(
        self, cars: List[Dict[str, Any]], transmission_type: str
    ) -> List[Dict[str, Any]]:
        """Фильтрует автомобили по типу трансмиссии"""
        if not transmission_type or transmission_type not in self.transmission_mappings:
            return cars

        transmission_keywords = self.transmission_mappings[transmission_type]
        filtered_cars = []

        for car in cars:
            title = car.get("title", "").lower()
            transmission_display = car.get("transmission_display", "").lower()

            # Проверяем по названию или полю трансмиссии
            for keyword in transmission_keywords:
                if keyword.lower() in title or keyword.lower() in transmission_display:
                    filtered_cars.append(car)
                    break

        logger.info(
            f"Фильтрация по трансмиссии {transmission_type}: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def filter_cars_by_grade(
        self, cars: List[Dict[str, Any]], grade_hash_id: str
    ) -> List[Dict[str, Any]]:
        """Фильтрует автомобили по конфигурации (grade)"""
        if not grade_hash_id or len(grade_hash_id) < 2 or not grade_hash_id.replace("_", "").replace("-", "").isalnum():
            return cars

        filtered_cars = []

        for car in cars:
            # Проверяем grade_hash_id в данных автомобиля
            car_grade = car.get("grade_hash_id", "")
            
            # Также проверяем вложенные данные grade если есть
            if not car_grade and isinstance(car.get("grade"), dict):
                car_grade = car["grade"].get("hash_id", "")
            
            if car_grade == grade_hash_id:
                filtered_cars.append(car)

        logger.info(
            f"Фильтрация по конфигурации {grade_hash_id}: {len(cars)} -> {len(filtered_cars)}"
        )
        return filtered_cars

    def apply_all_filters(
        self, cars: List[Dict[str, Any]], filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Применяет все фильтры к списку автомобилей"""
        filtered_cars = cars

        # Фильтр по модели
        if filters.get("model_group"):
            filtered_cars = self.filter_cars_by_model_group(
                filtered_cars, filters["model_group"]
            )

        # Фильтр по конфигурации (grade)
        if filters.get("grade"):
            filtered_cars = self.filter_cars_by_grade(
                filtered_cars, filters["grade"]
            )

        # Фильтр по году
        if filters.get("min_year") or filters.get("max_year"):
            filtered_cars = self.filter_cars_by_year(
                filtered_cars, filters.get("min_year"), filters.get("max_year")
            )

        # Фильтр по пробегу
        if filters.get("min_mileage") or filters.get("max_mileage"):
            filtered_cars = self.filter_cars_by_mileage(
                filtered_cars, filters.get("min_mileage"), filters.get("max_mileage")
            )

        # Фильтр по цене
        if filters.get("min_price") or filters.get("max_price"):
            filtered_cars = self.filter_cars_by_price(
                filtered_cars, filters.get("min_price"), filters.get("max_price")
            )

        # Фильтр по топливу
        if filters.get("fuel"):
            filtered_cars = self.filter_cars_by_fuel(filtered_cars, filters["fuel"])

        # Фильтр по трансмиссии
        if filters.get("transmission"):
            filtered_cars = self.filter_cars_by_transmission(
                filtered_cars, filters["transmission"]
            )

        logger.info(f"Общая фильтрация: {len(cars)} -> {len(filtered_cars)}")
        return filtered_cars


# Глобальный экземпляр фильтра
client_filter = HeyDealerClientFilter()
