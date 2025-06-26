from typing import List, Dict, Any, Optional
import logging
from app.models.heydealer import (
    HeyDealerCar,
    HeyDealerCarList,
    CarDetail,
    Auction,
    CarEtc,
    InteriorInfo,
    AuctionTag,
    HeyDealerDetailedCar,
    DetailedCarDetail,
    DetailedAuction,
    DetailedCarEtc,
    ColorInfo,
    ImageGroup,
    AdvancedOption,
    CarSpec,
    AccidentRepair,
    AccidentInfo,
    CarHistory,
    VehicleInformation,
    InspectedCondition,
    AuctionHistory,
    UserHistory,
)

logger = logging.getLogger(__name__)


class HeyDealerParser:
    """Парсер для обработки данных HeyDealer API"""

    @staticmethod
    def parse_car_list(raw_data: List[Dict[str, Any]]) -> Optional[HeyDealerCarList]:
        """
        Парсит список автомобилей из ответа HeyDealer API

        Args:
            raw_data: Сырые данные от API

        Returns:
            Обработанный список автомобилей или None при ошибке
        """
        try:
            if not raw_data:
                logger.warning("Получен пустой список автомобилей")
                return HeyDealerCarList(cars=[], total_count=0, page=1)

            cars = []
            for car_data in raw_data:
                try:
                    car = HeyDealerParser._parse_single_car(car_data)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.error(
                        f"Ошибка парсинга автомобиля {car_data.get('hash_id', 'unknown')}: {e}"
                    )
                    continue

            return HeyDealerCarList(
                cars=cars,
                total_count=len(cars),
                page=1,  # API не возвращает информацию о странице в списке
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга списка автомобилей: {e}")
            return None

    @staticmethod
    def parse_car_list_with_pagination(
        raw_data: List[Dict[str, Any]], total_count: int, page: int, page_size: int
    ) -> Optional[HeyDealerCarList]:
        """
        Парсит список автомобилей с информацией о пагинации из HTTP заголовков

        Args:
            raw_data: Сырые данные от API
            total_count: Общее количество автомобилей из заголовка X-Pagination-Count
            page: Номер текущей страницы
            page_size: Размер страницы из заголовка X-Pagination-Page-Size

        Returns:
            Обработанный список автомобилей с правильной пагинацией или None при ошибке
        """
        try:
            if not raw_data:
                logger.warning("Получен пустой список автомобилей")
                return HeyDealerCarList(cars=[], total_count=total_count, page=page)

            cars = []
            for car_data in raw_data:
                try:
                    car = HeyDealerParser._parse_single_car(car_data)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.error(
                        f"Ошибка парсинга автомобиля {car_data.get('hash_id', 'unknown')}: {e}"
                    )
                    continue

            logger.info(
                f"Парсинг завершен: {len(cars)} автомобилей, страница {page}, общее количество {total_count}"
            )

            return HeyDealerCarList(
                cars=cars,
                total_count=total_count,
                page=page,
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга списка автомобилей с пагинацией: {e}")
            return None

    @staticmethod
    def _parse_single_car(car_data: Dict[str, Any]) -> Optional[HeyDealerCar]:
        """
        Парсит данные одного автомобиля

        Args:
            car_data: Данные автомобиля от API

        Returns:
            Обработанные данные автомобиля или None при ошибке
        """
        try:
            # Парсим детальную информацию
            detail_data = car_data.get("detail", {})

            # Парсим interior_info если есть
            interior_info = None
            if detail_data.get("interior_info"):
                interior_info = InteriorInfo(
                    text=detail_data.get("interior_info", {}).get("text", ""),
                    codes=detail_data.get("interior_info", {}).get("codes", []),
                )

            detail = CarDetail(
                full_name=detail_data.get("full_name"),
                model_part_name=detail_data.get("model_part_name"),
                grade_part_name=detail_data.get("grade_part_name"),
                brand_image_url=detail_data.get("brand_image_url"),
                main_image_url=detail_data.get("main_image_url"),
                image_urls=detail_data.get("image_urls", []),
                car_number=detail_data.get("car_number"),
                year=detail_data.get("year"),
                initial_registration_date=detail_data.get("initial_registration_date"),
                mileage=detail_data.get("mileage"),
                interior_info=interior_info,
                location=detail_data.get("location"),
                short_location=detail_data.get("short_location"),
                short_location_first_part_name=detail_data.get(
                    "short_location_first_part_name"
                ),
                is_pre_inspected=detail_data.get("is_pre_inspected"),
                dealer_zero_type=detail_data.get("dealer_zero_type"),
                zero_type=detail_data.get("zero_type"),
            )

            # Парсим информацию об аукционе
            auction_data = car_data.get("auction", {})
            tags = []
            for tag_data in auction_data.get("tags", []):
                tag = AuctionTag(
                    text=tag_data.get("text", ""),
                    short_text=tag_data.get("short_text", ""),
                    style=tag_data.get("style", ""),
                )
                tags.append(tag)

            auction = Auction(
                auction_type=auction_data.get("auction_type", ""),
                approved_at=auction_data.get("approved_at", ""),
                end_at=auction_data.get("end_at", ""),
                ended_at=auction_data.get("ended_at"),
                invalid_at=auction_data.get("invalid_at"),
                expire_at=auction_data.get("expire_at"),
                expired_at=auction_data.get("expired_at"),
                selected_at=auction_data.get("selected_at"),
                max_bids_count=auction_data.get("max_bids_count", 0),
                bids_count=auction_data.get("bids_count", 0),
                selected_bid=auction_data.get("selected_bid"),
                highest_bid=auction_data.get("highest_bid"),
                my_bid=auction_data.get("my_bid"),
                my_bid_price=auction_data.get("my_bid_price"),
                is_visited=auction_data.get("is_visited", False),
                is_starred=auction_data.get("is_starred", False),
                is_additional_information=auction_data.get(
                    "is_additional_information", False
                ),
                has_previous_bid=auction_data.get("has_previous_bid", False),
                category=auction_data.get("category", ""),
                tags=tags,
                desired_price=auction_data.get("desired_price"),
                previous_desired_price_diff=auction_data.get(
                    "previous_desired_price_diff"
                ),
            )

            # Парсим дополнительную информацию
            etc_data = car_data.get("etc", {})
            etc = CarEtc(
                is_associate_member_bid_unavailable=etc_data.get(
                    "is_associate_member_bid_unavailable", False
                )
            )

            return HeyDealerCar(
                hash_id=car_data.get("hash_id", ""),
                status=car_data.get("status", ""),
                status_display=car_data.get("status_display", ""),
                detail=detail,
                auction=auction,
                etc=etc,
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга автомобиля: {e}")
            return None

    @staticmethod
    def normalize_car_data(car: HeyDealerCar) -> Dict[str, Any]:
        """
        Нормализует данные автомобиля в общий формат для всех аукционов

        Args:
            car: Автомобиль HeyDealer

        Returns:
            Нормализованные данные автомобиля
        """
        try:
            # Безопасное извлечение данных с проверками на None
            detail = car.detail if car.detail else None
            auction = car.auction if car.auction else None
            interior_info = (
                detail.interior_info if detail and detail.interior_info else None
            )

            return {
                "id": getattr(car, "hash_id", None),
                "lot_number": getattr(car, "hash_id", None),
                "auction_name": "HeyDealer",
                "title": detail.full_name if detail else None,
                "model": detail.full_name if detail else None,
                "year": detail.year if detail else None,
                "mileage": detail.mileage if detail else None,
                "location": detail.short_location if detail else None,
                "status": getattr(car, "status_display", None),
                "auction_type": auction.auction_type if auction else None,
                "end_time": auction.end_at if auction else None,
                "current_price": auction.desired_price if auction else None,
                "price": auction.desired_price if auction else None,
                "bid_count": auction.bids_count if auction else 0,
                "max_bids": auction.max_bids_count if auction else 0,
                "images": detail.image_urls if detail and detail.image_urls else [],
                "main_image": detail.main_image_url if detail else None,
                "brand_image": detail.brand_image_url if detail else None,
                "interior": interior_info.text if interior_info else None,
                "is_inspected": detail.is_pre_inspected if detail else False,
                "tags": (
                    [tag.text for tag in auction.tags]
                    if auction and auction.tags
                    else []
                ),
                "car_number": detail.car_number if detail else None,
                "registration_date": (
                    detail.initial_registration_date if detail else None
                ),
                "fuel_type": None,  # Добавляем для совместимости с тестами
            }
        except Exception as e:
            logger.error(
                f"Ошибка нормализации данных автомобиля {getattr(car, 'hash_id', 'unknown')}: {e}"
            )
            return {
                "id": None,
                "lot_number": None,
                "auction_name": "HeyDealer",
                "title": None,
                "model": None,
                "year": None,
                "mileage": None,
                "location": None,
                "status": None,
                "auction_type": None,
                "end_time": None,
                "current_price": None,
                "price": None,
                "bid_count": 0,
                "max_bids": 0,
                "images": [],
                "main_image": None,
                "brand_image": None,
                "interior": None,
                "is_inspected": False,
                "tags": [],
                "car_number": None,
                "registration_date": None,
                "fuel_type": None,
            }

    @staticmethod
    def format_response_data(
        cars: List[HeyDealerCar], total_count: int, page: int = 1
    ) -> Dict[str, Any]:
        """
        Форматирует данные для итогового ответа API

        Args:
            cars: Список автомобилей
            total_count: Общее количество
            page: Номер страницы

        Returns:
            Отформатированные данные
        """
        normalized_cars = []
        for car in cars:
            normalized = HeyDealerParser.normalize_car_data(car)
            if normalized:
                normalized_cars.append(normalized)

        # Вычисляем информацию о пагинации
        page_size = 20  # Стандартный размер страницы HeyDealer
        total_pages = (
            max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 1
        )

        return {
            "cars": normalized_cars,
            "total_count": total_count,
            "current_page": page,
            "total_pages": total_pages,
            "page_size": page_size,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_items": total_count,
                "page_size": page_size,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "auction_name": "HeyDealer",
            "success": True,
            "message": f"Успешно получено {len(normalized_cars)} автомобилей",
        }

    @staticmethod
    def parse_detailed_car(raw_data: Dict[str, Any]) -> Optional[HeyDealerDetailedCar]:
        """
        Парсит детальную информацию об автомобиле

        Args:
            raw_data: Сырые данные от API

        Returns:
            Детальная информация об автомобиле или None при ошибке
        """
        try:
            if not raw_data:
                logger.warning("Получены пустые данные автомобиля")
                return None

            # Парсим детальную информацию
            detail_data = raw_data.get("detail", {})

            # Парсим группы изображений
            image_groups = []
            for group_data in detail_data.get("image_groups", []):
                image_group = ImageGroup(
                    type=group_data.get("type", ""),
                    name=group_data.get("name", ""),
                    image_urls=group_data.get("image_urls", []),
                    count=group_data.get("count", 0),
                    condition_types=group_data.get("condition_types", []),
                )
                image_groups.append(image_group)

            # Парсим расширенные опции
            advanced_options = []
            for option_data in detail_data.get("advanced_options", []):
                option = AdvancedOption(
                    hash_id=option_data.get("hash_id", ""),
                    name=option_data.get("name", ""),
                    choice=option_data.get("choice"),
                    availability=option_data.get("availability", ""),
                    availability_for_display=option_data.get(
                        "availability_for_display", ""
                    ),
                    category=option_data.get("category", ""),
                    category_display=option_data.get("category_display", ""),
                    is_preview=option_data.get("is_preview", False),
                    choices=option_data.get("choices", []),
                    is_user_selectable=option_data.get("is_user_selectable", False),
                    is_auto_choice=option_data.get("is_auto_choice", False),
                )
                advanced_options.append(option)

            # Парсим ремонт после аварий
            accident_repairs = []
            for repair_data in detail_data.get("accident_repairs", []):
                repair = AccidentRepair(
                    part=repair_data.get("part", ""),
                    repair=repair_data.get("repair", ""),
                )
                accident_repairs.append(repair)

            # Парсим историю аварий
            accident_list = []
            carhistory_data = detail_data.get("carhistory", {})
            for accident_data in carhistory_data.get("my_car_accident_list", []):
                accident = AccidentInfo(
                    description=accident_data.get("description", ""),
                    insurance_money_display=accident_data.get(
                        "insurance_money_display", ""
                    ),
                    insurance_money=accident_data.get("insurance_money", 0),
                    accident_date=accident_data.get("accident_date", ""),
                    accident_type=accident_data.get("accident_type", ""),
                    is_severe_accident=accident_data.get("is_severe_accident", False),
                    amount=accident_data.get("amount", 0),
                )
                accident_list.append(accident)

            # Парсим историю автомобиля
            carhistory = CarHistory(
                result_code=carhistory_data.get("result_code", ""),
                car_number=carhistory_data.get("car_number", ""),
                year=carhistory_data.get("year", 0),
                car_type=carhistory_data.get("car_type", ""),
                use=carhistory_data.get("use", ""),
                displacement=carhistory_data.get("displacement", 0),
                model_group=carhistory_data.get("model_group", ""),
                initial_registration_date=carhistory_data.get(
                    "initial_registration_date", ""
                ),
                fuel=carhistory_data.get("fuel", ""),
                fuel_display=carhistory_data.get("fuel_display", ""),
                shape=carhistory_data.get("shape", ""),
                car_number_changed_count=carhistory_data.get(
                    "car_number_changed_count", 0
                ),
                owner_changed_count=carhistory_data.get("owner_changed_count", 0),
                my_car_accident_count=carhistory_data.get("my_car_accident_count", 0),
                other_car_accident_count=carhistory_data.get(
                    "other_car_accident_count", 0
                ),
                my_car_accident_cost=carhistory_data.get("my_car_accident_cost", 0),
                stolen_count=carhistory_data.get("stolen_count", 0),
                total_loss_count=carhistory_data.get("total_loss_count", 0),
                flooded_count=carhistory_data.get("flooded_count", 0),
                my_car_accident_list=accident_list,
            )

            # Парсим информацию о ТС
            vehicle_info_data = detail_data.get("vehicle_information", {})
            vehicle_information = VehicleInformation(
                is_erased=vehicle_info_data.get("is_erased", False),
                car_number=vehicle_info_data.get("car_number", ""),
                car_name=vehicle_info_data.get("car_name", ""),
                car_type=vehicle_info_data.get("car_type", ""),
                vin=vehicle_info_data.get("vin", ""),
                purpose=vehicle_info_data.get("purpose", ""),
                year=vehicle_info_data.get("year", 0),
                color=vehicle_info_data.get("color", ""),
                registration_type=vehicle_info_data.get("registration_type", ""),
                initial_registration_date=vehicle_info_data.get(
                    "initial_registration_date", ""
                ),
                manufactured_date=vehicle_info_data.get("manufactured_date", ""),
                inspection_valid_from=vehicle_info_data.get(
                    "inspection_valid_from", ""
                ),
                inspection_valid_until=vehicle_info_data.get(
                    "inspection_valid_until", ""
                ),
                mileage=vehicle_info_data.get("mileage", 0),
            )

            # Парсим проверенное состояние
            condition_data = detail_data.get("inspected_condition", {})
            inspected_condition = InspectedCondition(
                front_tire=condition_data.get("front_tire", 0),
                rear_tire=condition_data.get("rear_tire", 0),
                wheel_scratch=condition_data.get("wheel_scratch", 0),
                outer_panel_scratch=condition_data.get("outer_panel_scratch", 0),
                has_leakage=condition_data.get("has_leakage", False),
                has_dashboard_warning=condition_data.get(
                    "has_dashboard_warning", False
                ),
                has_option_malfunction=condition_data.get(
                    "has_option_malfunction", False
                ),
                comment=condition_data.get("comment", ""),
            )

            detail = DetailedCarDetail(
                detail_hash_id=detail_data.get("detail_hash_id", ""),
                model_hash_id=detail_data.get("model_hash_id", ""),
                full_name=detail_data.get("full_name", ""),
                full_name_without_brand=detail_data.get("full_name_without_brand", ""),
                is_detail_verified=detail_data.get("is_detail_verified", False),
                model_part_name=detail_data.get("model_part_name", ""),
                grade_part_name=detail_data.get("grade_part_name", ""),
                brand_name=detail_data.get("brand_name", ""),
                brand_image_url=detail_data.get("brand_image_url", ""),
                main_image_url=detail_data.get("main_image_url", ""),
                image_urls=detail_data.get("image_urls", []),
                image_groups=image_groups,
                car_number=detail_data.get("car_number", ""),
                year=detail_data.get("year", 0),
                initial_registration_date=detail_data.get(
                    "initial_registration_date", ""
                ),
                mileage=detail_data.get("mileage", 0),
                color=detail_data.get("color", ""),
                interior=detail_data.get("interior", ""),
                color_info=ColorInfo(
                    text=detail_data.get("color_info", {}).get("text", ""),
                    codes=detail_data.get("color_info", {}).get("codes", []),
                ),
                interior_info=InteriorInfo(
                    text=detail_data.get("interior_info", {}).get("text", ""),
                    codes=detail_data.get("interior_info", {}).get("codes", []),
                ),
                location=detail_data.get("location", ""),
                short_location=detail_data.get("short_location", ""),
                short_location_first_part_name=detail_data.get(
                    "short_location_first_part_name", ""
                ),
                payment=detail_data.get("payment", ""),
                payment_display=detail_data.get("payment_display", ""),
                fuel=detail_data.get("fuel", ""),
                fuel_display=detail_data.get("fuel_display", ""),
                transmission=detail_data.get("transmission", ""),
                transmission_display=detail_data.get("transmission_display", ""),
                accident=detail_data.get("accident"),
                accident_display=detail_data.get("accident_display"),
                accident_description=detail_data.get("accident_description", ""),
                accident_repairs=accident_repairs,
                accident_repairs_summary=detail_data.get(
                    "accident_repairs_summary", ""
                ),
                accident_repairs_summary_display=detail_data.get(
                    "accident_repairs_summary_display", ""
                ),
                is_accident_image_visible=detail_data.get(
                    "is_accident_image_visible", False
                ),
                is_advanced_options=detail_data.get("is_advanced_options", False),
                advanced_options=advanced_options,
                description=detail_data.get("description"),
                car_description=detail_data.get("car_description", ""),
                customer_comment=detail_data.get("customer_comment", ""),
                inspector_comment=detail_data.get("inspector_comment", ""),
                comment=detail_data.get("comment", ""),
                car_spec=CarSpec(
                    title=detail_data.get("car_spec", {}).get("title", ""),
                    description=detail_data.get("car_spec", {}).get("description", ""),
                ),
                carhistory=carhistory,
                vehicle_information=vehicle_information,
                phone_number=detail_data.get("phone_number"),
                is_reverse_year=detail_data.get("is_reverse_year", False),
                inspected_condition=inspected_condition,
                is_pre_inspected=detail_data.get("is_pre_inspected", False),
                dealer_zero_type=detail_data.get("dealer_zero_type"),
                zero_type=detail_data.get("zero_type", ""),
                early_scrap_display=detail_data.get("early_scrap_display", ""),
                is_operation_unavailable=detail_data.get(
                    "is_operation_unavailable", False
                ),
                operation_unavailable_reasons=detail_data.get(
                    "operation_unavailable_reasons", []
                ),
                standard_new_car_price=detail_data.get("standard_new_car_price", 0),
            )

            # Парсим информацию об аукционе
            auction_data = raw_data.get("auction", {})

            # Парсим историю аукционов
            auction_histories = []
            for history_data in auction_data.get("auction_histories", []):
                history = AuctionHistory(
                    date=history_data.get("date", ""),
                    highest_bid_price=history_data.get("highest_bid_price", 0),
                    bids_count=history_data.get("bids_count", 0),
                )
                auction_histories.append(history)

            # Парсим историю пользователя
            user_history_data = auction_data.get("user_history", {})
            user_history = UserHistory(
                cars_count=user_history_data.get("cars_count", 0),
                traded_cars_count=user_history_data.get("traded_cars_count", 0),
            )

            auction = DetailedAuction(
                auction_type=auction_data.get("auction_type", ""),
                visits_count=auction_data.get("visits_count", 0),
                approved_at=auction_data.get("approved_at", ""),
                end_at=auction_data.get("end_at", ""),
                ended_at=auction_data.get("ended_at"),
                invalid_at=auction_data.get("invalid_at"),
                expire_at=auction_data.get("expire_at"),
                expired_at=auction_data.get("expired_at"),
                selected_at=auction_data.get("selected_at"),
                bids=auction_data.get("bids", []),
                max_bids_count=auction_data.get("max_bids_count", 0),
                bids_count=auction_data.get("bids_count", 0),
                selected_bid=auction_data.get("selected_bid"),
                highest_bid=auction_data.get("highest_bid"),
                my_bid=auction_data.get("my_bid"),
                my_bid_price=auction_data.get("my_bid_price"),
                is_starred=auction_data.get("is_starred", False),
                is_additional_information=auction_data.get(
                    "is_additional_information", False
                ),
                has_previous_bid=auction_data.get("has_previous_bid", False),
                category=auction_data.get("category", ""),
                is_bid_unavailable=auction_data.get("is_bid_unavailable", False),
                bid_unavailable_message=auction_data.get("bid_unavailable_message"),
                desired_price=auction_data.get("desired_price", 0),
                auction_histories=auction_histories,
                user_history=user_history,
            )

            # Парсим дополнительную информацию
            etc_data = raw_data.get("etc", {})
            etc = DetailedCarEtc(
                has_corporate_owner=etc_data.get("has_corporate_owner", False),
                revision=etc_data.get("revision", 0),
            )

            return HeyDealerDetailedCar(
                hash_id=raw_data.get("hash_id", ""),
                status=raw_data.get("status", ""),
                status_display=raw_data.get("status_display", ""),
                detail=detail,
                auction=auction,
                etc=etc,
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга детальной информации автомобиля: {e}")
            return None

    @staticmethod
    def parse_detailed_car_simple(raw_data: Dict[str, Any]) -> Optional[HeyDealerCar]:
        """
        Упрощенный парсинг детальной информации об автомобиле (используя базовую модель)

        Args:
            raw_data: Сырые данные от API

        Returns:
            Базовая информация об автомобиле или None при ошибке
        """
        try:
            if not raw_data:
                logger.warning("Получены пустые данные автомобиля")
                return None

            # Адаптируем детальные данные к формату списка
            adapted_data = HeyDealerParser._adapt_detail_to_list_format(raw_data)

            # Используем существующий метод для парсинга
            return HeyDealerParser._parse_single_car(adapted_data)

        except Exception as e:
            logger.error(f"Ошибка упрощенного парсинга автомобиля: {e}")
            return None

    @staticmethod
    def _adapt_detail_to_list_format(detail_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Адаптирует данные детальной страницы к формату списка автомобилей

        Args:
            detail_data: Данные детальной страницы

        Returns:
            Адаптированные данные в формате списка
        """
        try:
            # Базовые поля остаются без изменений
            adapted = {
                "hash_id": detail_data.get("hash_id", ""),
                "status": detail_data.get("status", ""),
                "status_display": detail_data.get("status_display", ""),
                "detail": detail_data.get("detail", {}),
                "auction": detail_data.get("auction", {}),
                "etc": detail_data.get("etc", {}),
            }

            # Убеждаемся, что в auction есть нужное поле tags (если его нет)
            if "tags" not in adapted["auction"]:
                adapted["auction"]["tags"] = []

            # Убеждаемся, что есть поле is_visited в auction
            if "is_visited" not in adapted["auction"]:
                adapted["auction"]["is_visited"] = False

            return adapted

        except Exception as e:
            logger.error(f"Ошибка адаптации данных: {e}")
            return detail_data  # Возвращаем оригинальные данные при ошибке

    @staticmethod
    def parse_detailed_car_direct(raw_data: Dict[str, Any]) -> Optional[HeyDealerCar]:
        """
        Прямой парсинг детальной информации об автомобиле

        Args:
            raw_data: Сырые данные от API

        Returns:
            Информация об автомобиле или None при ошибке
        """
        try:
            if not raw_data:
                logger.warning("Получены пустые данные автомобиля")
                return None

            # Отладочная информация
            logger.info(f"Парсинг автомобиля {raw_data.get('hash_id', 'unknown')}")
            detail_data = raw_data.get("detail", {})
            logger.info(f"Detail data keys: {list(detail_data.keys())[:10]}")
            logger.info(f"Full name: {detail_data.get('full_name')}")
            logger.info(f"Year: {detail_data.get('year')}")
            logger.info(f"Mileage: {detail_data.get('mileage')}")

            # Парсим детальную информацию напрямую
            detail = CarDetail(
                full_name=detail_data.get("full_name", ""),
                model_part_name=detail_data.get("model_part_name", ""),
                grade_part_name=detail_data.get("grade_part_name", ""),
                brand_image_url=detail_data.get("brand_image_url", ""),
                main_image_url=detail_data.get("main_image_url", ""),
                image_urls=detail_data.get("image_urls", []),
                car_number=detail_data.get("car_number", ""),
                year=detail_data.get("year", 0),
                initial_registration_date=detail_data.get(
                    "initial_registration_date", ""
                ),
                mileage=detail_data.get("mileage", 0),
                interior_info=InteriorInfo(
                    text=detail_data.get("interior_info", {}).get("text", ""),
                    codes=detail_data.get("interior_info", {}).get("codes", []),
                ),
                location=detail_data.get("location", ""),
                short_location=detail_data.get("short_location", ""),
                short_location_first_part_name=detail_data.get(
                    "short_location_first_part_name", ""
                ),
                is_pre_inspected=detail_data.get("is_pre_inspected", False),
                dealer_zero_type=detail_data.get("dealer_zero_type"),
                zero_type=detail_data.get("zero_type"),
            )

            # Парсим информацию об аукционе напрямую
            auction_data = raw_data.get("auction", {})

            auction = Auction(
                auction_type=auction_data.get("auction_type", ""),
                approved_at=auction_data.get("approved_at", ""),
                end_at=auction_data.get("end_at", ""),
                ended_at=auction_data.get("ended_at"),
                invalid_at=auction_data.get("invalid_at"),
                expire_at=auction_data.get("expire_at"),
                expired_at=auction_data.get("expired_at"),
                selected_at=auction_data.get("selected_at"),
                max_bids_count=auction_data.get("max_bids_count", 0),
                bids_count=auction_data.get("bids_count", 0),
                selected_bid=auction_data.get("selected_bid"),
                highest_bid=auction_data.get("highest_bid"),
                my_bid=auction_data.get("my_bid"),
                my_bid_price=auction_data.get("my_bid_price"),
                is_visited=auction_data.get("visits_count", 0)
                > 0,  # Адаптируем visits_count к is_visited
                is_starred=auction_data.get("is_starred", False),
                is_additional_information=auction_data.get(
                    "is_additional_information", False
                ),
                has_previous_bid=auction_data.get("has_previous_bid", False),
                category=auction_data.get("category", ""),
                tags=[],  # Пока оставляем пустым
                desired_price=auction_data.get("desired_price"),
                previous_desired_price_diff=auction_data.get(
                    "previous_desired_price_diff"
                ),
            )

            # Парсим дополнительную информацию
            etc_data = raw_data.get("etc", {})
            etc = CarEtc(
                is_associate_member_bid_unavailable=etc_data.get(
                    "is_associate_member_bid_unavailable", False
                )
            )

            result = HeyDealerCar(
                hash_id=raw_data.get("hash_id", ""),
                status=raw_data.get("status", ""),
                status_display=raw_data.get("status_display", ""),
                detail=detail,
                auction=auction,
                etc=etc,
            )

            logger.info(
                f"Успешно спарсен автомобиль {result.hash_id}: {result.detail.full_name}"
            )
            return result

        except Exception as e:
            logger.error(f"Ошибка прямого парсинга автомобиля: {e}")
            import traceback

            logger.error(f"Трассировка: {traceback.format_exc()}")
            return None

    # === МЕТОДЫ ДЛЯ ПАРСИНГА ФИЛЬТРОВ ===

    def parse_brands(
        self, brands_data: List[Dict[str, Any]]
    ) -> "HeyDealerBrandsResponse":
        """Парсинг списка марок"""
        from app.models.heydealer import HeyDealerBrandsResponse, HeyDealerBrand

        try:
            parsed_brands = []

            for brand in brands_data:
                parsed_brand = HeyDealerBrand(
                    hash_id=brand.get("hash_id", ""),
                    name=brand.get("name", ""),
                    is_domestic=brand.get("is_domestic", False),
                    image_url=brand.get("image_url", ""),
                    count=brand.get("count", 0),
                    is_subscribed=brand.get("is_subscribed"),
                    has_subscription=brand.get("has_subscription"),
                    can_subscribe=brand.get("can_subscribe"),
                )
                parsed_brands.append(parsed_brand)

            logger.info(f"Парсинг марок завершен: {len(parsed_brands)} элементов")
            return HeyDealerBrandsResponse(
                success=True, data=parsed_brands, message="Марки успешно получены"
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге марок: {str(e)}")
            return HeyDealerBrandsResponse(success=False, data=[], message=str(e))

    def parse_brand_detail(
        self, brand_data: Dict[str, Any]
    ) -> "HeyDealerBrandDetailResponse":
        """Парсинг деталей марки с моделями"""
        from app.models.heydealer import HeyDealerBrandDetailResponse

        try:
            parsed_data = {
                "brand_info": {
                    "hash_id": brand_data.get("hash_id", ""),
                    "name": brand_data.get("name", ""),
                    "is_domestic": brand_data.get("is_domestic", False),
                    "image_url": brand_data.get("image_url", ""),
                    "count": brand_data.get("count", 0),
                },
                "model_groups": [],
            }

            # Парсим группы моделей
            model_groups = brand_data.get("model_groups", [])
            for model_group in model_groups:
                parsed_model = {
                    "hash_id": model_group.get("hash_id", ""),
                    "name": model_group.get("name", ""),
                    "count": model_group.get("count", 0),
                    "is_subscribed": model_group.get("is_subscribed"),
                    "has_subscription": model_group.get("has_subscription"),
                }
                parsed_data["model_groups"].append(parsed_model)

            logger.info(
                f"Парсинг деталей марки завершен: {len(parsed_data['model_groups'])} моделей"
            )
            return HeyDealerBrandDetailResponse(
                success=True, data=parsed_data, message="Модели марки успешно получены"
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге деталей марки: {str(e)}")
            return HeyDealerBrandDetailResponse(success=False, data={}, message=str(e))

    def parse_model_detail(
        self, model_data: Dict[str, Any]
    ) -> "HeyDealerModelDetailResponse":
        """Парсинг деталей модели с поколениями"""
        from app.models.heydealer import HeyDealerModelDetailResponse

        try:
            parsed_data = {
                "model_info": {
                    "hash_id": model_data.get("hash_id", ""),
                    "name": model_data.get("name", ""),
                    "count": model_data.get("count", 0),
                },
                "models": [],
            }

            # Парсим поколения
            models = model_data.get("models", [])
            for model in models:
                parsed_generation = {
                    "hash_id": model.get("hash_id", ""),
                    "name": model.get("name", ""),
                    "start_date": model.get("start_date"),
                    "end_date": model.get("end_date"),
                    "count": model.get("count", 0),
                    "is_subscribed": model.get("is_subscribed"),
                }
                parsed_data["models"].append(parsed_generation)

            logger.info(
                f"Парсинг деталей модели завершен: {len(parsed_data['models'])} поколений"
            )
            return HeyDealerModelDetailResponse(
                success=True,
                data=parsed_data,
                message="Поколения модели успешно получены",
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге деталей модели: {str(e)}")
            return HeyDealerModelDetailResponse(success=False, data={}, message=str(e))

    def parse_grade_detail(
        self, grade_data: Dict[str, Any]
    ) -> "HeyDealerGradeDetailResponse":
        """Парсинг деталей поколения с конфигурациями"""
        from app.models.heydealer import HeyDealerGradeDetailResponse

        try:
            parsed_data = {
                "generation_info": {
                    "hash_id": grade_data.get("hash_id", ""),
                    "name": grade_data.get("name", ""),
                    "start_date": grade_data.get("start_date"),
                    "end_date": grade_data.get("end_date"),
                    "count": grade_data.get("count", 0),
                },
                "grades": [],
            }

            # Парсим конфигурации
            grades = grade_data.get("grades", [])
            for grade in grades:
                parsed_config = {
                    "hash_id": grade.get("hash_id", ""),
                    "name": grade.get("name", ""),
                    "count": grade.get("count", 0),
                    "fuel_display": grade.get("fuel_display", ""),
                    "fuel_color_code": grade.get("fuel_color_code", ""),
                }
                parsed_data["grades"].append(parsed_config)

            logger.info(
                f"Парсинг деталей поколения завершен: {len(parsed_data['grades'])} конфигураций"
            )
            return HeyDealerGradeDetailResponse(
                success=True,
                data=parsed_data,
                message="Конфигурации модели успешно получены",
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге деталей поколения: {str(e)}")
            return HeyDealerGradeDetailResponse(success=False, data={}, message=str(e))

    def parse_filtered_cars(self, cars_data) -> "HeyDealerListResponse":
        """Парсинг отфильтрованного списка автомобилей"""
        from app.models.heydealer import HeyDealerListResponse

        try:
            # API возвращает массив напрямую
            if isinstance(cars_data, list):
                cars_list = cars_data
            else:
                # Если это объект, ищем результаты в разных полях
                cars_list = cars_data.get("results", cars_data.get("data", []))

            parsed_cars = []

            for car_data in cars_list:
                # Используем существующий метод _parse_single_car
                parsed_car = HeyDealerParser._parse_single_car(car_data)
                if parsed_car:
                    parsed_cars.append(parsed_car)

            logger.info(
                f"Парсинг отфильтрованных автомобилей завершен: {len(parsed_cars)} элементов"
            )
            return HeyDealerListResponse(
                success=True, data=parsed_cars, message="Автомобили успешно получены"
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге отфильтрованных автомобилей: {str(e)}")
            return HeyDealerListResponse(success=False, data=[], message=str(e))

    def parse_available_filters(
        self, filters_data: Dict[str, Any]
    ) -> "HeyDealerFiltersResponse":
        """Парсинг доступных фильтров"""
        from app.models.heydealer import (
            HeyDealerFiltersResponse,
            HeyDealerAvailableFilters,
            ApprovedAtFilter,
            YearRange,
            LocationFilter,
            FilterOption,
        )

        try:
            # Парсим фильтры по времени одобрения
            approved_at_filters = []
            for item in filters_data.get("approved_at", []):
                approved_at_filters.append(
                    ApprovedAtFilter(
                        min_approved_at=item.get("min_approved_at"),
                        max_approved_at=item.get("max_approved_at"),
                        count=item.get("count"),
                        key=item.get("key", ""),
                        title=item.get("title", ""),
                        description=item.get("description"),
                    )
                )

            # Парсим диапазон годов
            year_data = filters_data.get("year", {})
            year_range = YearRange(
                min=year_data.get("min", 1990), max=year_data.get("max", 2025)
            )

            # Парсим фильтры местоположения
            location_filters = []
            for item in filters_data.get("location_first_part", []):
                if item:  # Пропускаем пустые объекты
                    location_filters.append(
                        LocationFilter(value=item.get("value"), name=item.get("name"))
                    )

            # Парсим простые фильтры
            def parse_simple_filters(filter_list):
                return [
                    FilterOption(name=item["name"], value=item["value"])
                    for item in filter_list
                ]

            transmission_filters = parse_simple_filters(
                filters_data.get("transmission", [])
            )
            payment_filters = parse_simple_filters(filters_data.get("payment", []))
            car_type_filters = parse_simple_filters(filters_data.get("car_type", []))
            car_segment_filters = parse_simple_filters(
                filters_data.get("car_segment", [])
            )
            fuel_filters = parse_simple_filters(filters_data.get("fuel", []))
            mileage_group_filters = parse_simple_filters(
                filters_data.get("mileage_group", [])
            )
            accident_group_filters = parse_simple_filters(
                filters_data.get("accident_group", [])
            )
            accident_repairs_summary_filters = parse_simple_filters(
                filters_data.get("accident_repairs_summary", [])
            )
            wheel_drive_filters = parse_simple_filters(
                filters_data.get("wheel_drive", [])
            )
            my_car_accident_cost_filters = parse_simple_filters(
                filters_data.get("my_car_accident_cost", [])
            )
            owner_change_record_filters = parse_simple_filters(
                filters_data.get("owner_change_record", [])
            )
            use_record_filters = parse_simple_filters(
                filters_data.get("use_record", [])
            )
            special_accident_record_filters = parse_simple_filters(
                filters_data.get("special_accident_record", [])
            )
            operation_availability_filters = parse_simple_filters(
                filters_data.get("operation_availability", [])
            )

            # Пробег (список чисел)
            mileage_list = filters_data.get("mileage", [])

            # Создаем объект с доступными фильтрами
            available_filters = HeyDealerAvailableFilters(
                approved_at=approved_at_filters,
                year=year_range,
                location_first_part=location_filters,
                transmission=transmission_filters,
                payment=payment_filters,
                car_type=car_type_filters,
                car_segment=car_segment_filters,
                fuel=fuel_filters,
                mileage=mileage_list,
                mileage_group=mileage_group_filters,
                accident_group=accident_group_filters,
                accident_repairs_summary=accident_repairs_summary_filters,
                wheel_drive=wheel_drive_filters,
                my_car_accident_cost=my_car_accident_cost_filters,
                owner_change_record=owner_change_record_filters,
                use_record=use_record_filters,
                special_accident_record=special_accident_record_filters,
                operation_availability=operation_availability_filters,
            )

            logger.info("Парсинг доступных фильтров завершен успешно")
            return HeyDealerFiltersResponse(
                success=True,
                data=available_filters,
                message="Доступные фильтры успешно получены",
            )

        except Exception as e:
            logger.error(f"Ошибка при парсинге доступных фильтров: {str(e)}")
            return HeyDealerFiltersResponse(
                success=False,
                data=HeyDealerAvailableFilters(
                    approved_at=[],
                    year=YearRange(min=1990, max=2025),
                    location_first_part=[],
                    transmission=[],
                    payment=[],
                    car_type=[],
                    car_segment=[],
                    fuel=[],
                    mileage=[],
                    mileage_group=[],
                    accident_group=[],
                    accident_repairs_summary=[],
                    wheel_drive=[],
                    my_car_accident_cost=[],
                    owner_change_record=[],
                    use_record=[],
                    special_accident_record=[],
                    operation_availability=[],
                ),
                message=str(e),
            )
