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
        """Извлекает бренд и модель из названия [BRAND] Model"""
        try:
            import re

            # Ищем паттерн [BRAND] Model
            match = re.match(r"\[([^\]]+)\]\s*(.+)", car_name)
            if match:
                brand = match.group(1).strip()
                model = match.group(2).strip()
                return brand, model
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

            # Парсим данные по порядку: год, КПП, топливо, объем, пробег, оценка
            year = 0
            transmission = ""
            fuel_type = ""
            engine_volume = ""
            mileage = ""
            condition_grade = GlovisCarCondition.A4

            if len(span_texts) >= 1:
                try:
                    year = int(span_texts[0])
                except:
                    pass

            if len(span_texts) >= 2:
                transmission = span_texts[1].strip()

            if len(span_texts) >= 3:
                fuel_type = span_texts[2].strip()

            if len(span_texts) >= 4:
                engine_volume = span_texts[3].strip()

            if len(span_texts) >= 5:
                mileage = span_texts[4].strip()

            if len(span_texts) >= 6:
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
