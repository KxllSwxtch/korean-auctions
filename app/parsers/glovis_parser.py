"""
Парсер HTML данных аукциона SSANCAR (используем имя Glovis для API совместимости)
"""

import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup, Tag

from app.models.glovis import (
    GlovisCar,
    GlovisResponse,
    GlovisLocation,
    GlovisCarCondition,
    GlovisError,
    SSANCARManufacturer,
    SSANCARModel,
    SSANCARFuelType,
    SSANCARColor,
    SSANCARTransmission,
    SSANCARConditionGrade,
    SSANCARWeek,
)
from app.models.glovis_filters import GlovisManufacturer, GlovisModel, GlovisDetailModel
from app.core.logging import get_logger

logger = get_logger("ssancar_parser")


class GlovisParser:
    """Парсер HTML данных аукциона SSANCAR (сохраняем имя для совместимости)"""

    def __init__(self, base_url: str = "https://www.ssancar.com"):
        self.base_url = base_url.rstrip("/")

    def parse_car_list(
        self, html_content: str, page: int = 0, week_no: str = "2"
    ) -> GlovisResponse:
        """
        Парсит HTML страницу со списком автомобилей SSANCAR

        Args:
            html_content: HTML содержимое ответа от SSANCAR
            page: Номер текущей страницы (начинается с 0)
            week_no: Номер недели аукциона

        Returns:
            GlovisResponse: Объект с распарсенными данными
        """
        try:
            logger.info(
                f"🔍 Парсинг списка автомобилей SSANCAR (страница {page}, неделя {week_no})"
            )

            soup = BeautifulSoup(html_content, "html.parser")
            cars = []

            # Ищем все элементы <li> с автомобилями
            car_items = soup.find_all("li")

            if not car_items:
                logger.warning("⚠️ Не найдено автомобилей в HTML")
                return GlovisResponse(
                    success=True,
                    message="Автомобили не найдены",
                    total_count=0,
                    cars=[],
                    current_page=page,
                    page_size=15,
                    week_number=week_no,
                    source="SSANCAR",
                )

            for item in car_items:
                try:
                    car = self._parse_single_car(item)
                    if car:
                        # Добавляем информацию о странице и неделе
                        car.auction_number = week_no
                        cars.append(car)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга автомобиля: {e}")
                    continue

            total_count = len(cars)
            page_size = 15  # Стандартный размер страницы SSANCAR

            # Рассчитываем пагинацию
            total_pages = None
            has_next_page = (
                total_count == page_size
            )  # Если получили полную страницу, может быть следующая
            has_prev_page = page > 0

            logger.info(f"✅ Успешно распарсено {total_count} автомобилей")

            return GlovisResponse(
                success=True,
                message=f"Успешно получено {total_count} автомобилей",
                total_count=total_count,
                cars=cars,
                current_page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next_page=has_next_page,
                has_prev_page=has_prev_page,
                week_number=week_no,
                source="SSANCAR",
            )

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга списка автомобилей: {e}")
            return GlovisResponse(
                success=False,
                message=f"Ошибка парсинга: {str(e)}",
                total_count=0,
                cars=[],
                current_page=page,
                page_size=15,
                week_number=week_no,
                source="SSANCAR",
            )

    def _parse_single_car(self, item: Tag) -> Optional[GlovisCar]:
        """
        Парсит один элемент автомобиля из HTML структуры SSANCAR

        Args:
            item: BeautifulSoup Tag с информацией об автомобиле

        Returns:
            Optional[GlovisCar]: Объект автомобиля или None если не удалось распарсить
        """
        try:
            # Ищем ссылку на детальную страницу
            link = item.find("a", href=True)
            if not link:
                return None

            detail_url = link.get("href", "")
            if not detail_url or "car_view.php" not in detail_url:
                return None

            # Извлекаем car_no из URL
            car_no = self._extract_car_no(detail_url)

            # Ищем секцию с текстом
            text_area = item.find("div", class_="text_area")
            if not text_area:
                return None

            # Извлекаем Stock NO и название
            stock_no, car_name, brand, model = self._parse_title_section(text_area)

            # Извлекаем технические характеристики
            year, transmission, fuel_type, engine_volume, mileage, condition_grade = (
                self._parse_details_section(text_area)
            )

            # Извлекаем цену
            starting_price = self._parse_price_section(text_area)

            # Извлекаем изображение
            main_image_url = self._parse_image_section(item)

            # Создаем объект автомобиля
            car = GlovisCar(
                entry_number=stock_no,
                car_name=car_name,
                brand=brand,
                model=model,
                year=year,
                transmission=transmission,
                fuel_type=fuel_type,
                engine_volume=engine_volume,
                mileage=mileage,
                condition_grade=condition_grade,
                starting_price=starting_price,
                currency="USD",
                main_image_url=main_image_url,
                detail_url=(
                    detail_url
                    if detail_url.startswith("http")
                    else f"{self.base_url}{detail_url}"
                ),
                car_no=car_no,
                location=GlovisLocation.SSANCAR,
                # Эмулируем идентификаторы для совместимости
                gn=car_no or "",
                rc="SSANCAR",
                acc="1",
                atn="1",
                prodmancd=brand or "",
                reprcarcd=model or "",
                detacarcd=stock_no,
                cargradcd=condition_grade.value if condition_grade else "",
            )

            return car

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга автомобиля: {e}")
            return None

    def _extract_car_no(self, detail_url: str) -> Optional[str]:
        """Извлекает car_no из URL детальной страницы"""
        try:
            import re

            match = re.search(r"car_no=(\d+)", detail_url)
            return match.group(1) if match else None
        except:
            return None

    def _parse_title_section(self, text_area: Tag) -> tuple:
        """Парсит секцию с названием и Stock NO"""
        try:
            title_section = text_area.find("p", class_="tit")
            if not title_section:
                return "", "", "", ""

            # Извлекаем Stock NO
            stock_span = title_section.find("span", class_="num")
            stock_no = stock_span.get_text().strip() if stock_span else ""

            # Извлекаем название автомобиля
            name_span = title_section.find("span", class_="name")
            car_name = name_span.get_text().strip() if name_span else ""

            # Извлекаем бренд и модель из названия [BRAND] Model
            brand, model = self._extract_brand_model(car_name)

            return stock_no, car_name, brand, model

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга заголовка: {e}")
            return "", "", "", ""

    def _extract_brand_model(self, car_name: str) -> tuple:
        """Извлекает бренд и модель из названия"""
        try:
            # В SSANCAR названия имеют формат: "INTERACTIVE K5 (G) 2.0 Signature"
            # где K5 - это модель KIA
            
            # Определяем бренд по модели
            if "K5" in car_name:
                return "KIA", car_name
            elif "SONATA" in car_name:
                return "HYUNDAI", car_name
            elif "GRANDEUR" in car_name:
                return "HYUNDAI", car_name
            elif "AVANTE" in car_name:
                return "HYUNDAI", car_name
            elif "PALISADE" in car_name:
                return "HYUNDAI", car_name
            elif "SPORTAGE" in car_name:
                return "KIA", car_name
            elif "SORENTO" in car_name:
                return "KIA", car_name
            
            # Если не удалось определить, возвращаем пустой бренд
            return "", car_name
        except:
            return "", car_name

    def _parse_details_section(self, text_area: Tag) -> tuple:
        """Парсит секцию с техническими характеристиками"""
        try:
            detail_ul = text_area.find("ul", class_="detail")
            if not detail_ul:
                return 0, "", "", "", "", GlovisCarCondition.A4

            detail_li = detail_ul.find("li")
            if not detail_li:
                return 0, "", "", "", "", GlovisCarCondition.A4

            # Получаем все span элементы
            spans = detail_li.find_all("span")

            # Фильтруем пустые span'ы
            span_texts = [
                span.get_text().strip() for span in spans if span.get_text().strip()
            ]

            # Парсим данные по порядку из HTML: год, пробег, КПП, цвет, топливо, оценка
            year = 0
            transmission = ""
            fuel_type = ""
            engine_volume = ""
            mileage = ""
            condition_grade = GlovisCarCondition.A4

            # В SSANCAR порядок: Year, Mileage (Km), Transmission, Color, Fuel Type, Grade
            if len(span_texts) >= 1:
                try:
                    year = int(span_texts[0])
                except:
                    pass

            if len(span_texts) >= 2:
                # Пробег (например: "67,321 Km")
                mileage = span_texts[1].strip()

            if len(span_texts) >= 3:
                # КПП (Automatic, Manual и т.д.)
                transmission = span_texts[2].strip()

            if len(span_texts) >= 4:
                # Цвет (пропускаем, так как он не используется в основной модели)
                pass

            if len(span_texts) >= 5:
                # Тип топлива (Gasoline, Diesel и т.д.)
                fuel_type = span_texts[4].strip()

            if len(span_texts) >= 6:
                # Оценка состояния (D/C, A/1 и т.д.)
                grade_text = span_texts[5].strip()
                # Пытаемся найти соответствующую оценку
                for grade in GlovisCarCondition:
                    if grade.value == grade_text:
                        condition_grade = grade
                        break

            return (
                year,
                transmission,
                fuel_type,
                engine_volume,
                mileage,
                condition_grade,
            )

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга характеристик: {e}")
            return 0, "", "", "", "", GlovisCarCondition.A4

    def _parse_price_section(self, text_area: Tag) -> int:
        """Парсит секцию с ценой"""
        try:
            price_section = text_area.find("p", class_="money")
            if not price_section:
                return 0

            price_num = price_section.find("span", class_="num")
            if not price_num:
                return 0

            price_text = price_num.get_text().strip().replace(",", "")
            try:
                return int(price_text)
            except ValueError:
                return 0

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга цены: {e}")
            return 0

    def _parse_image_section(self, item: Tag) -> Optional[str]:
        """Парсит секцию с изображением"""
        try:
            img_area = item.find("div", class_="img_area")
            if not img_area:
                return None

            img = img_area.find("img")
            if not img:
                return None

            img_src = img.get("src", "")
            if img_src and img_src != "https://www.ssancar.com/img/no_image.png":
                return img_src

            return None

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга изображения: {e}")
            return None

    def get_test_data(self) -> GlovisResponse:
        """Возвращает тестовые данные для отладки"""
        logger.info("🧪 Возвращаем тестовые данные SSANCAR")

        test_cars = [
            GlovisCar(
                entry_number="2001",
                car_name="[HYUNDAI] NewClick 1.4 i Deluxe",
                brand="HYUNDAI",
                model="NewClick 1.4 i Deluxe",
                year=2010,
                transmission="A/T",
                fuel_type="Gasoline",
                engine_volume="1,399cc",
                mileage="72,698 Km",
                condition_grade=GlovisCarCondition.A1,
                starting_price=1541,
                currency="USD",
                main_image_url="https://img-auction.autobell.co.kr/test",
                detail_url="https://www.ssancar.com/page/car_view.php?car_no=1515765",
                car_no="1515765",
                location=GlovisLocation.SSANCAR,
                auction_number="2",
                gn="1515765",
                rc="SSANCAR",
                acc="1",
                atn="1",
                prodmancd="HYUNDAI",
                reprcarcd="NewClick",
                detacarcd="2001",
                cargradcd="A/1",
            ),
            GlovisCar(
                entry_number="2002",
                car_name="[HYUNDAI] GrandeurIG 3.0 GDi Exclusive Special",
                brand="HYUNDAI",
                model="GrandeurIG 3.0 GDi Exclusive Special",
                year=2018,
                transmission="A/T",
                fuel_type="Gasoline",
                engine_volume="2,999cc",
                mileage="70,917 Km",
                condition_grade=GlovisCarCondition.A6,
                starting_price=12334,
                currency="USD",
                main_image_url="https://img-auction.autobell.co.kr/test2",
                detail_url="https://www.ssancar.com/page/car_view.php?car_no=1515766",
                car_no="1515766",
                location=GlovisLocation.SSANCAR,
                auction_number="2",
                gn="1515766",
                rc="SSANCAR",
                acc="1",
                atn="1",
                prodmancd="HYUNDAI",
                reprcarcd="GrandeurIG",
                detacarcd="2002",
                cargradcd="A/6",
            ),
        ]

        return GlovisResponse(
            success=True,
            message="Тестовые данные SSANCAR",
            total_count=len(test_cars),
            cars=test_cars,
            current_page=0,
            page_size=15,
            total_pages=1,
            has_next_page=False,
            has_prev_page=False,
            week_number="2",
            source="SSANCAR",
        )

    def parse_manufacturers(self, html_content: str) -> List[GlovisManufacturer]:
        """
        Парсит список производителей из HTML страницы фильтров

        Args:
            html_content: HTML содержимое страницы с фильтрами

        Returns:
            List[GlovisManufacturer]: Список производителей
        """
        manufacturers = []

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Ищем все блоки производителей с классом "model-box"
            model_boxes = soup.find_all("div", class_="model-box")

            for box in model_boxes:
                try:
                    # Ищем checkbox с именем "arrProdmancd"
                    checkbox = box.find("input", {"name": "arrProdmancd"})
                    if not checkbox:
                        continue

                    # Извлекаем код производителя
                    prodmancd = checkbox.get("value", "")
                    if not prodmancd:
                        continue

                    # Извлекаем название производителя
                    name_span = box.find("span", id=f"corp_nm_{prodmancd}")
                    name = name_span.get_text().strip() if name_span else ""

                    # Извлекаем количество доступных автомобилей
                    count_span = box.find("span", id=f"corp_cnt_{prodmancd}")
                    count_text = count_span.get_text().strip() if count_span else "0"
                    count = int(count_text) if count_text.isdigit() else 0

                    # Проверяем, доступен ли производитель (не disabled)
                    enabled = not checkbox.get("disabled", False)

                    # Создаем объект производителя
                    manufacturer = GlovisManufacturer(
                        prodmancd=prodmancd, name=name, count=count, enabled=enabled
                    )

                    manufacturers.append(manufacturer)

                except Exception as e:
                    logger.error(f"Ошибка при парсинге производителя: {e}")
                    continue

            logger.info(f"✅ Парсинг производителей: найдено {len(manufacturers)}")
            return manufacturers

        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге производителей: {e}")
            return []

    def parse_models(self, json_response: Dict[str, Any]) -> List[GlovisModel]:
        """
        Парсит список моделей из JSON ответа API

        Args:
            json_response: JSON ответ от API carCorpModelList.do

        Returns:
            List[GlovisModel]: Список моделей
        """
        models = []

        try:
            # Извлекаем список из JSON структуры
            result = json_response.get("result", {})
            model_list = result.get("list", [])

            for item in model_list:
                try:
                    # Извлекаем данные модели
                    makeid = str(item.get("makeid", ""))
                    makenm = item.get("makenm", "")
                    targetcnt = item.get("targetcnt", 0)
                    prodmancd = result.get("prodmancd", "")

                    # Создаем код модели из makeid для совместимости
                    reprcarcd = makeid

                    model = GlovisModel(
                        makeid=makeid,
                        makenm=makenm,
                        reprcarcd=reprcarcd,
                        prodmancd=prodmancd,
                        targetcnt=targetcnt,
                    )

                    models.append(model)

                except Exception as e:
                    logger.error(f"Ошибка при парсинге модели: {e}")
                    continue

            logger.info(f"✅ Парсинг моделей: найдено {len(models)}")
            return models

        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге моделей: {e}")
            return []

    def parse_detail_models(
        self, json_response: Dict[str, Any]
    ) -> List[GlovisDetailModel]:
        """
        Парсит список детальных моделей из JSON ответа API

        Args:
            json_response: JSON ответ от API carModelDetailList.do

        Returns:
            List[GlovisDetailModel]: Список детальных моделей
        """
        detail_models = []

        try:
            # Извлекаем список из JSON структуры
            result = json_response.get("result", {})
            model_list = result.get("list", [])

            for item in model_list:
                try:
                    # Извлекаем данные детальной модели
                    makeid = str(item.get("makeid", ""))
                    makenm = item.get("makenm", "")
                    targetcnt = item.get("targetcnt", 0)

                    # Для детальных моделей используем makeid как detacarcd
                    detacarcd = makeid

                    # reprcarcd и prodmancd могут отсутствовать в детальных моделях
                    # Нужно будет передавать их из контекста запроса
                    reprcarcd = ""  # Будет заполнено из контекста
                    prodmancd = ""  # Будет заполнено из контекста

                    detail_model = GlovisDetailModel(
                        makeid=makeid,
                        makenm=makenm,
                        detacarcd=detacarcd,
                        reprcarcd=reprcarcd,
                        prodmancd=prodmancd,
                        targetcnt=targetcnt,
                    )

                    detail_models.append(detail_model)

                except Exception as e:
                    logger.error(f"Ошибка при парсинге детальной модели: {e}")
                    continue

            logger.info(f"✅ Парсинг детальных моделей: найдено {len(detail_models)}")
            return detail_models

        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге детальных моделей: {e}")
            return []

    # =============================================================================
    # SSANCAR FILTER PARSING METHODS
    # =============================================================================

    def get_static_manufacturers(self) -> List:
        """
        Возвращает статический список производителей SSANCAR
        Основан на анализе структуры данных SSANCAR
        """
        manufacturers = [
            SSANCARManufacturer(
                code="HYUNDAI", name="현대", name_en="Hyundai", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="KIA", name="기아", name_en="Kia", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="GENESIS",
                name="제네시스",
                name_en="Genesis",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="GM", name="한국GM", name_en="GM Korea", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="CHEVROLET",
                name="쉐보레",
                name_en="Chevrolet",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="TOYOTA", name="토요타", name_en="Toyota", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="LEXUS", name="렉서스", name_en="Lexus", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="HONDA", name="혼다", name_en="Honda", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="NISSAN", name="닛산", name_en="Nissan", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="INFINITI",
                name="인피니티",
                name_en="Infiniti",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="MAZDA", name="마쯔다", name_en="Mazda", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="SUBARU", name="스바루", name_en="Subaru", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="MITSUBISHI",
                name="미쯔비시",
                name_en="Mitsubishi",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="BMW", name="BMW", name_en="BMW", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="MERCEDES",
                name="메르세데스-벤츠",
                name_en="Mercedes-Benz",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="AUDI", name="아우디", name_en="Audi", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="VOLKSWAGEN",
                name="폭스바겐",
                name_en="Volkswagen",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="PORSCHE", name="포르쉐", name_en="Porsche", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="MINI", name="미니", name_en="Mini", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="VOLVO", name="볼보", name_en="Volvo", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="FORD", name="포드", name_en="Ford", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="LINCOLN", name="링컨", name_en="Lincoln", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="CADILLAC",
                name="캐딜락",
                name_en="Cadillac",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="TESLA", name="테슬라", name_en="Tesla", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="JAGUAR", name="재규어", name_en="Jaguar", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="LANDROVER",
                name="랜드로버",
                name_en="Land Rover",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="BENTLEY", name="벤틀리", name_en="Bentley", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="ROLLSROYCE",
                name="롤스로이스",
                name_en="Rolls-Royce",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="FERRARI", name="페라리", name_en="Ferrari", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="LAMBORGHINI",
                name="람보르기니",
                name_en="Lamborghini",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="MASERATI",
                name="마세라티",
                name_en="Maserati",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="ASTON_MARTIN",
                name="애스턴마틴",
                name_en="Aston Martin",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="MCLAREN", name="맥라렌", name_en="McLaren", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="JEEP", name="지프", name_en="Jeep", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="CHRYSLER",
                name="크라이슬러",
                name_en="Chrysler",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="DODGE", name="닷지", name_en="Dodge", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="RENAULT", name="르노", name_en="Renault", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="PEUGEOT", name="푸조", name_en="Peugeot", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="CITROEN",
                name="시트로엥",
                name_en="Citroën",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="FIAT", name="피아트", name_en="Fiat", count=0, enabled=True
            ),
            SSANCARManufacturer(
                code="ALFA_ROMEO",
                name="알파로메오",
                name_en="Alfa Romeo",
                count=0,
                enabled=True,
            ),
            SSANCARManufacturer(
                code="OTHERS", name="기타", name_en="Others", count=0, enabled=True
            ),
        ]

        logger.info(f"✅ Возвращено {len(manufacturers)} производителей SSANCAR")
        return manufacturers

    def get_static_fuel_types(self) -> List:
        """
        Возвращает статический список типов топлива SSANCAR
        """
        fuel_types = [
            SSANCARFuelType(code="gasoline", name="가솔린"),
            SSANCARFuelType(code="diesel", name="디젤"),
            SSANCARFuelType(code="hybrid", name="하이브리드"),
            SSANCARFuelType(code="electric", name="전기"),
            SSANCARFuelType(code="lpg", name="LPG"),
            SSANCARFuelType(code="other", name="기타"),
        ]

        logger.info(f"✅ Возвращено {len(fuel_types)} типов топлива SSANCAR")
        return fuel_types

    def get_static_colors(self) -> List:
        """
        Возвращает статический список цветов SSANCAR
        """
        colors = [
            SSANCARColor(code="white", name="흰색"),
            SSANCARColor(code="black", name="검은색"),
            SSANCARColor(code="silver", name="은색"),
            SSANCARColor(code="gray", name="회색"),
            SSANCARColor(code="red", name="빨간색"),
            SSANCARColor(code="blue", name="파란색"),
            SSANCARColor(code="green", name="초록색"),
            SSANCARColor(code="yellow", name="노란색"),
            SSANCARColor(code="brown", name="갈색"),
            SSANCARColor(code="orange", name="주황색"),
            SSANCARColor(code="gold", name="금색"),
            SSANCARColor(code="purple", name="보라색"),
            SSANCARColor(code="other", name="기타"),
        ]

        logger.info(f"✅ Возвращено {len(colors)} цветов SSANCAR")
        return colors

    def get_static_transmissions(self) -> List:
        """
        Возвращает статический список типов трансмиссии SSANCAR
        """
        transmissions = [
            SSANCARTransmission(code="AT", name="오토마틱 (A/T)"),
            SSANCARTransmission(code="MT", name="수동 (M/T)"),
            SSANCARTransmission(code="CVT", name="CVT"),
            SSANCARTransmission(code="AMT", name="AMT"),
            SSANCARTransmission(code="other", name="기타"),
        ]

        logger.info(f"✅ Возвращено {len(transmissions)} типов трансмиссии SSANCAR")
        return transmissions

    def get_static_condition_grades(self) -> List:
        """
        Возвращает статический список оценок состояния SSANCAR
        """
        grades = [
            SSANCARConditionGrade(code="A/1", name="A/1 - Отличное состояние"),
            SSANCARConditionGrade(code="A/2", name="A/2 - Очень хорошее состояние"),
            SSANCARConditionGrade(code="A/3", name="A/3 - Хорошее состояние"),
            SSANCARConditionGrade(
                code="A/4", name="A/4 - Удовлетворительное состояние"
            ),
            SSANCARConditionGrade(code="B/1", name="B/1 - Состояние ниже среднего"),
            SSANCARConditionGrade(code="B/2", name="B/2 - Плохое состояние"),
            SSANCARConditionGrade(code="B/3", name="B/3 - Очень плохое состояние"),
            SSANCARConditionGrade(code="C/1", name="C/1 - Критическое состояние"),
            SSANCARConditionGrade(
                code="C/2", name="C/2 - Неудовлетворительное состояние"
            ),
            SSANCARConditionGrade(code="D/1", name="D/1 - Аварийное состояние"),
        ]

        logger.info(f"✅ Возвращено {len(grades)} оценок состояния SSANCAR")
        return grades

    def get_static_weeks(self) -> List:
        """
        Возвращает статический список недель аукциона SSANCAR
        """
        weeks = [
            SSANCARWeek(number=1, name="1주차", active=True),
            SSANCARWeek(number=2, name="2주차", active=True),
            SSANCARWeek(number=3, name="3주차", active=True),
            SSANCARWeek(number=4, name="4주차", active=True),
        ]

        logger.info(f"✅ Возвращено {len(weeks)} недель аукциона SSANCAR")
        return weeks

    def parse_manufacturers_from_cars(self, cars_data: List[Dict[str, Any]]) -> List:
        """
        Извлекает список производителей из данных автомобилей SSANCAR
        """
        manufacturer_counts = {}

        try:
            for car in cars_data:
                brand = car.get("brand", "").upper()
                if brand and brand != "UNKNOWN":
                    if brand in manufacturer_counts:
                        manufacturer_counts[brand] += 1
                    else:
                        manufacturer_counts[brand] = 1

            manufacturers = []
            static_manufacturers = self.get_static_manufacturers()
            static_map = {m.code: m for m in static_manufacturers}

            for brand, count in manufacturer_counts.items():
                if brand in static_map:
                    manufacturer = static_map[brand]
                    manufacturer.count = count
                    manufacturers.append(manufacturer)
                else:
                    # Новый производитель, не в списке
                    manufacturers.append(
                        SSANCARManufacturer(
                            code=brand,
                            name=brand,
                            name_en=brand,
                            count=count,
                            enabled=True,
                        )
                    )

            # Сортируем по количеству автомобилей
            manufacturers.sort(key=lambda x: x.count, reverse=True)

            logger.info(
                f"✅ Извлечено {len(manufacturers)} производителей из данных автомобилей"
            )
            return manufacturers

        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении производителей: {e}")
            return self.get_static_manufacturers()

    def parse_models_from_cars(
        self, cars_data: List[Dict[str, Any]], manufacturer_code: str
    ) -> List:
        """
        Извлекает список моделей для указанного производителя из данных автомобилей SSANCAR
        """
        model_counts = {}

        try:
            for car in cars_data:
                brand = car.get("brand", "").upper()
                model = car.get("model", "").strip()

                if brand == manufacturer_code.upper() and model:
                    if model in model_counts:
                        model_counts[model] += 1
                    else:
                        model_counts[model] = 1

            models = []
            for model_name, count in model_counts.items():
                models.append(
                    SSANCARModel(
                        code=model_name.upper().replace(" ", "_"),
                        name=model_name,
                        manufacturer_code=manufacturer_code,
                        count=count,
                    )
                )

            # Сортируем по количеству автомобилей
            models.sort(key=lambda x: x.count, reverse=True)

            logger.info(
                f"✅ Извлечено {len(models)} моделей для производителя {manufacturer_code}"
            )
            return models

        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении моделей: {e}")
            return []

    def analyze_car_data_for_filters(
        self, cars_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Анализирует данные автомобилей для определения доступных фильтров
        """
        try:
            analysis = {
                "total_cars": len(cars_data),
                "manufacturers": {},
                "years": {"min": 9999, "max": 0},
                "prices": {"min": float("inf"), "max": 0},
                "fuel_types": set(),
                "transmissions": set(),
                "condition_grades": set(),
            }

            for car in cars_data:
                # Анализ производителей
                brand = car.get("brand", "").upper()
                if brand and brand != "UNKNOWN":
                    analysis["manufacturers"][brand] = (
                        analysis["manufacturers"].get(brand, 0) + 1
                    )

                # Анализ годов
                year = car.get("year")
                if year and isinstance(year, int):
                    analysis["years"]["min"] = min(analysis["years"]["min"], year)
                    analysis["years"]["max"] = max(analysis["years"]["max"], year)

                # Анализ цен
                price = car.get("price")
                if price and isinstance(price, (int, float)):
                    analysis["prices"]["min"] = min(analysis["prices"]["min"], price)
                    analysis["prices"]["max"] = max(analysis["prices"]["max"], price)

                # Анализ топлива
                fuel = car.get("fuel")
                if fuel:
                    analysis["fuel_types"].add(fuel.lower())

                # Анализ трансмиссии
                transmission = car.get("transmission")
                if transmission:
                    analysis["transmissions"].add(transmission.upper())

                # Анализ состояния
                condition = car.get("condition")
                if condition:
                    analysis["condition_grades"].add(condition)

            # Преобразуем sets в lists для JSON serialization
            analysis["fuel_types"] = list(analysis["fuel_types"])
            analysis["transmissions"] = list(analysis["transmissions"])
            analysis["condition_grades"] = list(analysis["condition_grades"])

            # Обрабатываем edge cases
            if analysis["years"]["min"] == 9999:
                analysis["years"] = {"min": 1990, "max": 2025}

            if analysis["prices"]["min"] == float("inf"):
                analysis["prices"] = {"min": 0, "max": 100000}

            logger.info(
                f"✅ Анализ данных автомобилей завершен: {analysis['total_cars']} автомобилей"
            )
            return analysis

        except Exception as e:
            logger.error(f"❌ Ошибка при анализе данных автомобилей: {e}")
            return {
                "total_cars": 0,
                "manufacturers": {},
                "years": {"min": 1990, "max": 2025},
                "prices": {"min": 0, "max": 100000},
                "fuel_types": [],
                "transmissions": [],
                "condition_grades": [],
            }
