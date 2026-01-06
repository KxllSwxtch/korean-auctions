"""
HTML Parser for Green Heavy Equipment (4396200.com)
Parses list pages and detail pages from the website
"""

from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
import re
import logging

from app.models.green_equipment import (
    GreenEquipment,
    GreenEquipmentDetails,
    GreenEquipmentSpec,
    GreenEquipmentSeller,
    EQUIPMENT_CATEGORIES,
)

logger = logging.getLogger(__name__)

# Base URL for the website
BASE_URL = "https://www.4396200.com"


class GreenEquipmentParser:
    """Parser for Green Heavy Equipment HTML pages"""

    @staticmethod
    def parse_list_page(html_content: str, category_code: str) -> Tuple[List[GreenEquipment], int]:
        """
        Parse equipment listing page HTML

        Args:
            html_content: HTML content of the list page
            category_code: Category code (100-111)

        Returns:
            Tuple of (equipment list, total count)
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            equipment_list = []
            total_count = 0

            # Get category name from the category code
            category_info = EQUIPMENT_CATEGORIES.get(category_code, {})
            category_name = category_info.get("ko", "")

            # Find all equipment listing items
            # The items are in <li> elements within the listing container
            # Pattern: /sub8_1_vvv.html?pid=XXXXX

            # Try to find listing items by various patterns
            listing_items = soup.find_all('li')

            for item in listing_items:
                try:
                    # Look for links with pid parameter
                    links = item.find_all('a', href=re.compile(r'pid=\d+'))
                    if not links:
                        continue

                    # Extract equipment ID from first link
                    first_link = links[0]
                    href = first_link.get('href', '')
                    pid_match = re.search(r'pid=(\d+)', href)
                    if not pid_match:
                        continue

                    equipment_id = pid_match.group(1)

                    # Extract model name (usually in the second link text or strong element)
                    model = ""
                    for link in links:
                        link_text = link.get_text(strip=True)
                        # Skip price and condition links
                        if '가격' not in link_text and '급' not in link_text and link_text:
                            model = link_text
                            break

                    # Extract price
                    price = 0
                    price_krw = 0
                    price_link = item.find('a', string=re.compile(r'가격'))
                    if price_link:
                        price_text = price_link.get_text(strip=True)
                        price_match = re.search(r'([\d,]+)만원', price_text)
                        if price_match:
                            price_str = price_match.group(1).replace(',', '')
                            price = int(price_str)
                            price_krw = price * 10000

                    # Try alternative price extraction from strong element
                    if price == 0:
                        price_strong = item.find('strong', string=re.compile(r'[\d,]+만원'))
                        if price_strong:
                            price_match = re.search(r'([\d,]+)만원', price_strong.get_text(strip=True))
                            if price_match:
                                price_str = price_match.group(1).replace(',', '')
                                price = int(price_str)
                                price_krw = price * 10000

                    # Extract condition
                    condition = None
                    condition_link = item.find('a', string=re.compile(r'[AB]\+?급'))
                    if condition_link:
                        condition = condition_link.get_text(strip=True)

                    # Extract image URL
                    image_url = None
                    img_tag = item.find('img')
                    if img_tag:
                        src = img_tag.get('src', '')
                        if src:
                            if src.startswith('//'):
                                image_url = 'https:' + src
                            elif src.startswith('/'):
                                image_url = BASE_URL + src
                            elif src.startswith('http'):
                                image_url = src
                            else:
                                image_url = BASE_URL + '/' + src

                    # Skip if no model name or price
                    if not model or price == 0:
                        continue

                    # Create equipment object
                    equipment = GreenEquipment(
                        id=equipment_id,
                        category_code=category_code,
                        category_name=category_name,
                        model=model,
                        price=price,
                        price_krw=price_krw,
                        condition=condition,
                        image_url=image_url,
                        images=[image_url] if image_url else [],
                        url=f"{BASE_URL}/sub8_1_vvv.html?pid={equipment_id}",
                    )
                    equipment_list.append(equipment)

                except Exception as e:
                    logger.warning(f"Failed to parse list item: {e}")
                    continue

            # Try to get total count from page
            # Usually displayed somewhere on the page
            total_count = len(equipment_list)

            logger.info(f"Parsed {len(equipment_list)} equipment items from category {category_code}")
            return equipment_list, total_count

        except Exception as e:
            logger.error(f"Error parsing list page: {e}")
            return [], 0

    @staticmethod
    def parse_detail_page(html_content: str, equipment_id: str, category_code: str = "") -> Optional[GreenEquipmentDetails]:
        """
        Parse equipment detail page HTML

        Args:
            html_content: HTML content of the detail page
            equipment_id: Equipment ID (pid)
            category_code: Category code if known

        Returns:
            GreenEquipmentDetails object or None
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')

            # Get category name
            category_info = EQUIPMENT_CATEGORIES.get(category_code, {})
            category_name = category_info.get("ko", "")

            # Extract title/model name
            # Usually in a heading or title element
            model = ""
            title_element = soup.find('title')
            if title_element:
                title_text = title_element.get_text(strip=True)
                # Extract model from title (usually before ::)
                if '::' in title_text:
                    model = title_text.split('::')[0].strip()

            # Try to find model from page content
            if not model:
                # Look for h1, h2, or strong elements with model info
                for tag in ['h1', 'h2', 'h3', 'strong']:
                    element = soup.find(tag)
                    if element:
                        text = element.get_text(strip=True)
                        if text and len(text) < 100:  # Reasonable model name length
                            model = text
                            break

            # Extract price
            price = 0
            price_krw = 0
            price_pattern = re.compile(r'([\d,]+)\s*만원')
            price_elements = soup.find_all(string=price_pattern)
            for elem in price_elements:
                match = price_pattern.search(elem)
                if match:
                    price_str = match.group(1).replace(',', '')
                    price = int(price_str)
                    price_krw = price * 10000
                    break

            # Extract condition
            condition = None
            condition_pattern = re.compile(r'[AB]\+?급')
            condition_elements = soup.find_all(string=condition_pattern)
            for elem in condition_elements:
                match = condition_pattern.search(elem)
                if match:
                    condition = match.group()
                    break

            # Extract all images
            images = []
            img_tags = soup.find_all('img')
            for img in img_tags:
                src = img.get('src', '')
                if src and ('upload' in src or 'goods' in src or 'product' in src or 'equipment' in src):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = BASE_URL + src
                    elif not src.startswith('http'):
                        src = BASE_URL + '/' + src
                    if src not in images:
                        images.append(src)

            # Extract seller information
            seller = None
            phone_pattern = re.compile(r'(\d{2,4}[-.]?\d{3,4}[-.]?\d{4})')
            phone_matches = phone_pattern.findall(html_content)
            if phone_matches:
                # Filter out common non-phone numbers
                valid_phones = [p for p in phone_matches if len(p.replace('-', '').replace('.', '')) >= 9]
                if valid_phones:
                    seller = GreenEquipmentSeller(
                        phone=valid_phones[0],
                        phone2=valid_phones[1] if len(valid_phones) > 1 else None
                    )

            # Extract specifications
            spec = GreenEquipmentSpec(
                model=model,
            )

            # Try to extract year from model name or page content
            year_pattern = re.compile(r'(19|20)\d{2}')
            year_matches = year_pattern.findall(model + html_content[:5000])
            if year_matches:
                # Get the most likely year (recent years are more common)
                for year_str in year_matches:
                    year = int(year_str + year_matches[year_matches.index(year_str)][2:] if len(year_str) == 2 else year_str)
                    if 1980 <= year <= 2026:
                        spec.year = year
                        break

            # Try to extract manufacturer
            manufacturers = ['현대', '두산', '대우', '볼보', '삼성', '한라', '코마스', '히타치', '코벨코', '캐타필라', '얀마']
            for mfr in manufacturers:
                if mfr in model or mfr in html_content[:5000]:
                    spec.manufacturer = mfr
                    break

            # Extract description
            description = None
            # Look for description in common containers
            desc_containers = soup.find_all(['div', 'td', 'p'], class_=re.compile(r'desc|content|detail|info', re.I))
            for container in desc_containers:
                text = container.get_text(strip=True)
                if len(text) > 50:  # Reasonable description length
                    description = text[:1000]  # Limit length
                    break

            # Create details object
            details = GreenEquipmentDetails(
                id=equipment_id,
                category_code=category_code or "100",
                category_name=category_name,
                model=model or f"Equipment #{equipment_id}",
                price=price,
                price_krw=price_krw,
                condition=condition,
                spec=spec,
                seller=seller,
                images=images,
                description=description,
                url=f"{BASE_URL}/sub8_1_vvv.html?pid={equipment_id}",
            )

            logger.info(f"Parsed detail page for equipment {equipment_id}")
            return details

        except Exception as e:
            logger.error(f"Error parsing detail page for {equipment_id}: {e}")
            return None

    @staticmethod
    def parse_subcategories(html_content: str, category_code: str) -> List[dict]:
        """
        Parse subcategories from a category page

        Args:
            html_content: HTML content of the category page
            category_code: Parent category code

        Returns:
            List of subcategory dictionaries with code and name
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            subcategories = []

            # Find subcategory links
            # Pattern: sub8_1_s.html?cate_code=XXXXXX
            subcat_links = soup.find_all('a', href=re.compile(r'sub8_1_s\.html\?cate_code=\d+'))

            for link in subcat_links:
                href = link.get('href', '')
                code_match = re.search(r'cate_code=(\d+)', href)
                if code_match:
                    subcat_code = code_match.group(1)
                    subcat_name = link.get_text(strip=True)
                    if subcat_code and subcat_name:
                        subcategories.append({
                            'code': subcat_code,
                            'name': subcat_name,
                            'parent_code': category_code
                        })

            logger.info(f"Found {len(subcategories)} subcategories for category {category_code}")
            return subcategories

        except Exception as e:
            logger.error(f"Error parsing subcategories: {e}")
            return []

    @staticmethod
    def extract_equipment_count(html_content: str) -> int:
        """
        Extract total equipment count from page

        Args:
            html_content: HTML content

        Returns:
            Total count or 0 if not found
        """
        try:
            # Look for count patterns like "총 123건" or "Total: 123"
            count_patterns = [
                re.compile(r'총\s*(\d+)\s*건'),
                re.compile(r'Total[:\s]*(\d+)'),
                re.compile(r'(\d+)\s*건'),
            ]

            for pattern in count_patterns:
                match = pattern.search(html_content)
                if match:
                    return int(match.group(1))

            return 0

        except Exception as e:
            logger.error(f"Error extracting count: {e}")
            return 0


# Create singleton parser instance
green_equipment_parser = GreenEquipmentParser()
