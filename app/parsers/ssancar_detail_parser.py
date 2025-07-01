#!/usr/bin/env python3
"""
SSANCAR Car Detail Parser

Парсер для детальной страницы автомобиля SSANCAR.
Извлекает всю информацию об автомобиле включая:
- Основную информацию (stock_no, название, бренд, модель)
- Технические характеристики
- Фотографии
- Цену и время аукциона
"""

import re
from typing import List, Optional, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from app.models.glovis import SSANCARCarDetail
from app.core.logging import get_logger

logger = get_logger(__name__)


class SSANCARDetailParser:
    """Парсер для детальной страницы автомобиля SSANCAR"""

    def __init__(self, base_url: str = "https://www.ssancar.com"):
        self.base_url = base_url

    def parse_car_detail(
        self, html_content: str, car_no: str
    ) -> Optional[SSANCARCarDetail]:
        """
        Парсит HTML детальной страницы автомобиля SSANCAR

        Args:
            html_content: HTML контент страницы
            car_no: Номер автомобиля SSANCAR

        Returns:
            SSANCARCarDetail или None если парсинг не удался
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Основная информация
            car_detail = {
                "car_no": car_no,
                "stock_no": self._extract_stock_no(soup),
                "car_name": self._extract_car_name(soup),
                "detail_url": f"{self.base_url}/page/car_view.php?car_no={car_no}",
                "manager_url": self._extract_manager_url(soup),
                "images": self._extract_images(soup),
            }

            # Извлекаем бренд и модель из названия
            brand, model = self._extract_brand_and_model(car_detail["car_name"])
            car_detail["brand"] = brand
            car_detail["model"] = model

            # Технические характеристики
            tech_specs = self._extract_technical_specs(soup)
            car_detail.update(tech_specs)

            # Цена
            price_info = self._extract_price_info(soup)
            car_detail.update(price_info)

            # Информация об аукционе
            auction_info = self._extract_auction_info(soup)
            car_detail.update(auction_info)

            # Устанавливаем главное изображение
            if car_detail["images"]:
                car_detail["main_image"] = car_detail["images"][0]

            return SSANCARCarDetail(**car_detail)

        except Exception as e:
            logger.error(
                f"🚫 Ошибка парсинга детальной страницы для car_no={car_no}: {e}"
            )
            return None

    def _extract_stock_no(self, soup: BeautifulSoup) -> str:
        """Извлекает Stock NO"""
        try:
            stock_no_elem = soup.find("p", class_="num")
            if stock_no_elem:
                span = stock_no_elem.find("span")
                if span:
                    return span.get_text(strip=True)
        except Exception as e:
            logger.warning(f"Не удалось извлечь Stock NO: {e}")

        return ""

    def _extract_car_name(self, soup: BeautifulSoup) -> str:
        """Извлекает название автомобиля"""
        try:
            name_elem = soup.find("p", class_="name")
            if name_elem:
                span = name_elem.find("span")
                if span:
                    return span.get_text(strip=True)
        except Exception as e:
            logger.warning(f"Не удалось извлечь название автомобиля: {e}")

        return ""

    def _extract_brand_and_model(
        self, car_name: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Извлекает бренд и модель из названия автомобиля"""
        try:
            # Паттерн: [HYUNDAI] NewClick 1.4 i Deluxe
            match = re.match(r"\[([^\]]+)\]\s*(.+)", car_name)
            if match:
                brand = match.group(1).strip()
                model = match.group(2).strip()
                return brand, model
        except Exception as e:
            logger.warning(f"Не удалось извлечь бренд и модель из '{car_name}': {e}")

        return None, None

    def _extract_technical_specs(self, soup: BeautifulSoup) -> Dict[str, any]:
        """Извлекает технические характеристики"""
        specs = {}

        try:
            detail_elem = soup.find("ul", class_="detail")
            if detail_elem:
                # Получаем все span элементы с характеристиками
                spans = detail_elem.find_all("span")

                if len(spans) >= 6:
                    # Обрабатываем каждую характеристику
                    year_text = spans[0].get_text(strip=True)
                    transmission = spans[1].get_text(strip=True)
                    fuel_type = spans[2].get_text(strip=True)
                    engine_volume = spans[3].get_text(strip=True)
                    mileage = spans[4].get_text(strip=True)
                    condition_grade = spans[5].get_text(strip=True)

                    # Конвертируем год в число
                    try:
                        specs["year"] = int(year_text) if year_text.isdigit() else None
                    except:
                        specs["year"] = None

                    specs["transmission"] = transmission
                    specs["fuel_type"] = fuel_type
                    specs["engine_volume"] = engine_volume
                    specs["mileage"] = mileage
                    specs["condition_grade"] = condition_grade

        except Exception as e:
            logger.warning(f"Не удалось извлечь технические характеристики: {e}")

        return specs

    def _extract_price_info(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Извлекает информацию о цене"""
        price_info = {}

        try:
            money_elem = soup.find("p", class_="money")
            if money_elem:
                span = money_elem.find("span")
                if span:
                    price_text = span.get_text(strip=True)
                    price_info["starting_price"] = price_text

                    # Определяем валюту
                    if "$" in price_text:
                        price_info["currency"] = "USD"
                    elif "원" in price_text or "KRW" in price_text:
                        price_info["currency"] = "KRW"
                    else:
                        price_info["currency"] = "USD"  # По умолчанию

        except Exception as e:
            logger.warning(f"Не удалось извлечь информацию о цене: {e}")

        return price_info

    def _extract_auction_info(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Извлекает информацию об аукционе"""
        auction_info = {}

        try:
            # Извлекаем информацию о дате и времени из текста
            detail_elem = soup.find("p", class_="detail")
            if detail_elem:
                detail_text = detail_elem.get_text()

                # Ищем даты в тексте
                upload_match = re.search(
                    r"Upload\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}[AP]M)",
                    detail_text,
                )
                start_match = re.search(
                    r"Start\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}[AP]M)", detail_text
                )

                if upload_match:
                    auction_info["upload_date"] = upload_match.group(1)
                if start_match:
                    auction_info["auction_start_date"] = start_match.group(1)

            # Извлекаем оставшееся время
            timer_elem = soup.find("strong", class_="timer")
            if timer_elem:
                timer_text = timer_elem.get_text(strip=True)
                auction_info["auction_time_remaining"] = timer_text

        except Exception as e:
            logger.warning(f"Не удалось извлечь информацию об аукционе: {e}")

        return auction_info

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Извлекает список изображений автомобиля"""
        images = []

        try:
            # Ищем все слайды в swiper
            swiper_slides = soup.find_all("div", class_="swiper-slide")

            for slide in swiper_slides:
                img = slide.find("img")
                if img and img.get("src"):
                    src = img.get("src")
                    # Пропускаем заглушки и иконки
                    if (
                        "no_image" not in src
                        and "car_detail.svg" not in src
                        and src.startswith("http")
                    ):
                        images.append(src)

            logger.info(f"📸 Найдено {len(images)} изображений")

        except Exception as e:
            logger.warning(f"Не удалось извлечь изображения: {e}")

        return images

    def _extract_manager_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Извлекает ссылку на страницу менеджеров"""
        try:
            choice_box = soup.find("div", class_="choice_box")
            if choice_box:
                link = choice_box.find("a")
                if link and link.get("href"):
                    return urljoin(self.base_url, link.get("href"))
        except Exception as e:
            logger.warning(f"Не удалось извлечь ссылку на менеджеров: {e}")

        return None


def parse_ssancar_car_detail(
    html_content: str, car_no: str
) -> Optional[SSANCARCarDetail]:
    """
    Функция-обертка для парсинга детальной страницы автомобиля SSANCAR

    Args:
        html_content: HTML контент страницы
        car_no: Номер автомобиля SSANCAR

    Returns:
        SSANCARCarDetail или None
    """
    parser = SSANCARDetailParser()
    return parser.parse_car_detail(html_content, car_no)
