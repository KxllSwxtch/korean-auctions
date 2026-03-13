import re
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from loguru import logger

from app.models.happycar import HappyCarListItem, HappyCarDetail, HappyCarModelCategory


class HappyCarParser:
    """Pure HTML parser for HappyCar insurance auction pages.

    No HTTP calls — receives raw HTML strings, returns structured data.
    """

    BASE_URL = "https://www.happycarservice.com"

    def parse_car_list(self, html: str) -> Tuple[List[HappyCarListItem], int, List[HappyCarModelCategory]]:
        """Parse car list HTML from the AJAX endpoint.

        Returns:
            Tuple of (car_items, total_count, model_categories)
        """
        try:
            cars = []
            total_count = 0
            model_categories = []

            soup = BeautifulSoup(html, 'html.parser')

            # Extract total count from script: setTotalCount(NNN);
            total_match = re.search(r'setTotalCount\((\d+)\)', html)
            if total_match:
                total_count = int(total_match.group(1))
                logger.info(f"📊 Total count from setTotalCount: {total_count}")

            # Extract model categories from script: carModel_gubun('...');
            model_matches = re.findall(r"carModel_gubun\('([^']*)'\)", html)
            if model_matches:
                model_categories = self._parse_model_categories(model_matches)

            # Find all car list items
            car_items = soup.find_all('li')

            for item in car_items:
                try:
                    car = self._parse_single_car(item)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.error(f"Error parsing car item: {e}")
                    continue

            logger.info(f"✅ Parsed {len(cars)} cars from HTML (total: {total_count})")
            return cars, total_count, model_categories

        except Exception as e:
            logger.error(f"❌ Error parsing car list: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], 0, []

    def _parse_single_car(self, item) -> Optional[HappyCarListItem]:
        """Parse a single <li> element into a HappyCarListItem."""
        # Find the main link with idx parameter
        link = item.find('a', href=True)
        if not link:
            return None

        href = link.get('href', '')
        if 'ins_view.html' not in href and 'idx=' not in href:
            return None

        # Extract idx from href
        idx_match = re.search(r'idx=(\d+)', href)
        if not idx_match:
            return None
        idx = idx_match.group(1)

        # Extract image URL from div.img-wrap style background-image
        image_url = None
        img_wrap = item.find('div', class_='img-wrap')
        if img_wrap:
            style = img_wrap.get('style', '')
            bg_match = re.search(r"background-image\s*:\s*url\('?([^'\")\s]+)'?\)", style)
            if bg_match:
                img_path = bg_match.group(1)
                image_url = img_path if img_path.startswith('http') else f"{self.BASE_URL}{img_path}"

        # Fallback: try to find img tag
        if not image_url:
            img_tag = item.find('img')
            if img_tag and img_tag.get('src'):
                img_src = img_tag['src']
                image_url = img_src if img_src.startswith('http') else f"{self.BASE_URL}{img_src}"

        # Extract sale type from label.status1 or label.status2 etc.
        sale_type = ""
        for cls in ['status1', 'status2', 'status3', 'status4', 'status5']:
            label = item.find('label', class_=cls)
            if label:
                sale_type = label.get_text(strip=True)
                break
        if not sale_type:
            # Try any label element
            label = item.find('label')
            if label:
                sale_type = label.get_text(strip=True)

        # Extract title
        title = ""
        title_elem = item.find('strong', class_='title')
        if title_elem:
            title = title_elem.get_text(strip=True)
        if not title:
            title_elem = item.find(class_='title')
            if title_elem:
                title = title_elem.get_text(strip=True)

        # Extract registration number from span.subtitle
        registration_number = ""
        subtitle = item.find('span', class_='subtitle')
        if subtitle:
            registration_number = subtitle.get_text(strip=True)

        # Extract car specs from span.car-desc
        year = None
        fuel = None
        transmission = None
        displacement = None
        mileage = None

        car_desc = item.find('span', class_='car-desc')
        if car_desc:
            # Get all text segments between <em> separators
            desc_text = car_desc.get_text(separator='|', strip=True)
            parts = [p.strip() for p in desc_text.split('|') if p.strip()]

            for part in parts:
                if '년' in part and ('월' in part or re.match(r'\d{4}년', part)):
                    year = part
                elif part in ['LPG', '휘발유', '경유', '전기', '하이브리드', 'CNG', '수소', 'LNG']:
                    fuel = part
                elif part in ['오토', '수동', 'CVT', 'DCT', 'AT', 'MT']:
                    transmission = part
                elif 'cc' in part.lower():
                    displacement = part
                elif 'km' in part.lower() or part == '-':
                    mileage = part

        # Extract damage type (전손/분손)
        damage_type = None
        damage_spans = item.find_all('span')
        for span in damage_spans:
            span_text = span.get_text(strip=True)
            if span_text in ['전손', '분손']:
                damage_type = span_text
                break
        # Also check in usedcar-icon area
        icon_area = item.find(class_='usedcar-icon')
        if icon_area and not damage_type:
            icon_text = icon_area.get_text(strip=True)
            if '전손' in icon_text:
                damage_type = '전손'
            elif '분손' in icon_text:
                damage_type = '분손'

        # Extract auction info (deadline, min_bid, location) from div.auc-info
        deadline = None
        min_bid = None
        location = None

        auc_info = item.find('div', class_='auc-info')
        if auc_info:
            info_items = auc_info.find_all('p')
            for p in info_items:
                text = p.get_text(strip=True)
                # Deadline contains date pattern
                if re.search(r'\d{4}-\d{2}-\d{2}', text):
                    deadline = text
                # Min bid contains 원 (won)
                elif '원' in text:
                    min_bid = text
                # Location is remaining text (Korean city/province)
                elif text and not deadline and not min_bid:
                    location = text

        # Also try to find info in dt/dd or other patterns
        if not deadline:
            for elem in item.find_all(['span', 'p', 'dd']):
                text = elem.get_text(strip=True)
                if re.search(r'\d{4}-\d{2}-\d{2}.*\d{2}시', text):
                    deadline = text
                    break

        detail_url = f"{self.BASE_URL}/content/ins_view.html?idx={idx}"

        return HappyCarListItem(
            idx=idx,
            title=title,
            registration_number=registration_number,
            sale_type=sale_type,
            damage_type=damage_type,
            year=year,
            fuel=fuel,
            transmission=transmission,
            displacement=displacement,
            mileage=mileage,
            deadline=deadline,
            min_bid=min_bid,
            location=location,
            image_url=image_url,
            detail_url=detail_url,
        )

    def _parse_model_categories(self, raw_strings: List[str]) -> List[HappyCarModelCategory]:
        """Parse model category strings from JavaScript calls."""
        categories = []
        try:
            for raw in raw_strings:
                if not raw:
                    continue
                # Expected format: "name|count" or just "name"
                # The carModel_gubun might pass a serialized string
                parts = raw.split('|')
                if len(parts) >= 2:
                    name = parts[0].strip()
                    try:
                        count = int(parts[1].strip())
                    except ValueError:
                        count = 0
                    categories.append(HappyCarModelCategory(
                        name=name,
                        count=count,
                        search_key=name,
                    ))
                elif parts[0].strip():
                    categories.append(HappyCarModelCategory(
                        name=parts[0].strip(),
                        count=0,
                        search_key=parts[0].strip(),
                    ))
        except Exception as e:
            logger.error(f"❌ Error parsing model categories: {e}")

        return categories

    def parse_car_detail(self, html: str) -> Optional[HappyCarDetail]:
        """Parse the detail page HTML for a single car."""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract idx from the page URL or hidden fields
            idx = ""
            idx_match = re.search(r'idx=(\d+)', html)
            if idx_match:
                idx = idx_match.group(1)

            # Extract images from carousel/slider
            images = []
            # Try swiper slides
            for slide in soup.find_all('div', class_='swiper-slide'):
                img = slide.find('img')
                if img and img.get('src'):
                    src = img['src']
                    url = src if src.startswith('http') else f"{self.BASE_URL}{src}"
                    if 'no_image' not in url:
                        images.append(url)

            # Also try regular img tags in image containers
            if not images:
                for container_cls in ['img-wrap', 'img-area', 'photo-area', 'slider-area', 'gallery']:
                    container = soup.find(class_=container_cls)
                    if container:
                        for img in container.find_all('img'):
                            src = img.get('src', '')
                            if src and 'no_image' not in src:
                                url = src if src.startswith('http') else f"{self.BASE_URL}{src}"
                                images.append(url)

            # Also check for background-image URLs
            for div in soup.find_all('div', style=True):
                style = div.get('style', '')
                bg_matches = re.findall(r"background-image\s*:\s*url\('?([^'\")\s]+)'?\)", style)
                for bg_url in bg_matches:
                    url = bg_url if bg_url.startswith('http') else f"{self.BASE_URL}{bg_url}"
                    if 'no_image' not in url and url not in images:
                        images.append(url)

            # Extract title
            title = ""
            for cls in ['title', 'car-title', 'car-name']:
                elem = soup.find(class_=cls)
                if elem:
                    title = elem.get_text(strip=True)
                    break
            if not title:
                h2 = soup.find('h2')
                if h2:
                    title = h2.get_text(strip=True)

            # Extract sale type from status labels
            sale_type = ""
            for cls in ['status1', 'status2', 'status3', 'status4', 'status5']:
                label = soup.find('label', class_=cls)
                if label:
                    sale_type = label.get_text(strip=True)
                    break

            # Extract registration number
            registration_number = ""
            subtitle = soup.find('span', class_='subtitle')
            if subtitle:
                registration_number = subtitle.get_text(strip=True)

            # Parse spec table (차량 상세정보)
            specs = self._parse_specs_table(soup)

            # Parse damage description
            damage_description = None
            damage_section = soup.find(class_='damage-info')
            if damage_section:
                damage_description = damage_section.get_text(strip=True)
            if not damage_description:
                # Try finding by text content
                for elem in soup.find_all(['div', 'p', 'span']):
                    text = elem.get_text(strip=True)
                    if '사고내용' in text or '손상내용' in text or '피해내용' in text:
                        # Get the next sibling or parent's text
                        parent = elem.parent
                        if parent:
                            damage_description = parent.get_text(strip=True)
                        break

            # Parse insurance history (보험이력)
            insurance = self._parse_insurance_history(soup)

            # Parse vehicle info text block
            vehicle_info = self._parse_vehicle_info(soup)

            detail = HappyCarDetail(
                idx=idx,
                title=title or specs.get('title', ''),
                registration_number=registration_number or specs.get('registration_number', ''),
                sale_type=sale_type,
                year=specs.get('year'),
                transmission=specs.get('transmission'),
                fuel=specs.get('fuel'),
                displacement=specs.get('displacement'),
                mileage=specs.get('mileage'),
                min_bid=specs.get('min_bid'),
                location=specs.get('location'),
                deadline=specs.get('deadline'),
                cost_processing=specs.get('cost_processing'),
                damage_description=damage_description,
                car_name_full=vehicle_info.get('car_name_full'),
                msrp=vehicle_info.get('msrp'),
                vin=vehicle_info.get('vin'),
                form_number=vehicle_info.get('form_number'),
                form_year=vehicle_info.get('form_year'),
                first_registration=vehicle_info.get('first_registration'),
                color=vehicle_info.get('color'),
                actual_mileage=vehicle_info.get('actual_mileage'),
                inspection_validity=vehicle_info.get('inspection_validity'),
                plate_changes=insurance.get('plate_changes'),
                owner_changes=insurance.get('owner_changes'),
                my_damage=insurance.get('my_damage'),
                other_damage=insurance.get('other_damage'),
                images=images,
            )

            logger.info(f"✅ Parsed car detail for idx={idx}, title={title}")
            return detail

        except Exception as e:
            logger.error(f"❌ Error parsing car detail: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _parse_specs_table(self, soup) -> dict:
        """Parse the specs grid/table from detail page."""
        specs = {}

        # Try table-based layout
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                ths = row.find_all('th')
                tds = row.find_all('td')
                for th, td in zip(ths, tds):
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    self._map_spec_field(specs, key, value)

        # Try dl/dt/dd layout
        for dl in soup.find_all('dl'):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                key = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                self._map_spec_field(specs, key, value)

        # Try div-based key-value pairs
        for div in soup.find_all('div', class_='info-item'):
            label = div.find(class_='label')
            value_elem = div.find(class_='value')
            if label and value_elem:
                key = label.get_text(strip=True)
                value = value_elem.get_text(strip=True)
                self._map_spec_field(specs, key, value)

        return specs

    def _map_spec_field(self, specs: dict, key: str, value: str):
        """Map Korean spec field names to model fields."""
        if not key or not value or value == '-':
            return

        key_mapping = {
            '연식': 'year',
            '년식': 'year',
            '연월': 'year',
            '변속기': 'transmission',
            '변속': 'transmission',
            '연료': 'fuel',
            '유종': 'fuel',
            '배기량': 'displacement',
            '주행거리': 'mileage',
            '주행': 'mileage',
            '최저입찰가': 'min_bid',
            '최저가': 'min_bid',
            '입찰가': 'min_bid',
            '보관장소': 'location',
            '보관지': 'location',
            '위치': 'location',
            '마감일': 'deadline',
            '마감': 'deadline',
            '발생비용처리': 'cost_processing',
            '비용처리': 'cost_processing',
            '차명': 'title',
            '차량명': 'title',
            '등재번호': 'registration_number',
        }

        for korean_key, field_name in key_mapping.items():
            if korean_key in key:
                specs[field_name] = value
                return

    def _parse_insurance_history(self, soup) -> dict:
        """Parse insurance history section (보험이력)."""
        insurance = {}

        # Look for insurance history section
        for elem in soup.find_all(['div', 'section', 'table']):
            text = elem.get_text()
            if '보험이력' not in text and '사고이력' not in text:
                continue

            # Parse table rows within this section
            for row in elem.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)

                    if '번호변경' in key or '번판변경' in key:
                        insurance['plate_changes'] = value
                    elif '소유자변경' in key or '명의변경' in key:
                        insurance['owner_changes'] = value
                    elif '내차피해' in key or '자차' in key:
                        insurance['my_damage'] = value
                    elif '타차가해' in key or '상대' in key:
                        insurance['other_damage'] = value

            # Also try dl/dt/dd within the section
            for dt in elem.find_all('dt'):
                dd = dt.find_next_sibling('dd')
                if dd:
                    key = dt.get_text(strip=True)
                    value = dd.get_text(strip=True)
                    if '번호변경' in key:
                        insurance['plate_changes'] = value
                    elif '소유자변경' in key:
                        insurance['owner_changes'] = value
                    elif '내차피해' in key:
                        insurance['my_damage'] = value
                    elif '타차가해' in key:
                        insurance['other_damage'] = value

            break  # Found the insurance section, done

        return insurance

    def _parse_vehicle_info(self, soup) -> dict:
        """Parse vehicle info section (차량정보, VIN, MSRP, color, etc.)."""
        info = {}

        # Build a key-value map from all tables and definition lists
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    self._map_vehicle_field(info, key, value)

        for dl in soup.find_all('dl'):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                key = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                self._map_vehicle_field(info, key, value)

        return info

    def _map_vehicle_field(self, info: dict, key: str, value: str):
        """Map vehicle info Korean field names to model fields."""
        if not key or not value or value == '-':
            return

        field_mapping = {
            '차명': 'car_name_full',
            '차량명': 'car_name_full',
            '신차가격': 'msrp',
            '신차가': 'msrp',
            '차대번호': 'vin',
            'VIN': 'vin',
            '형식번호': 'form_number',
            '형식년도': 'form_year',
            '최초등록': 'first_registration',
            '최초등록일': 'first_registration',
            '색상': 'color',
            '실주행': 'actual_mileage',
            '실주행거리': 'actual_mileage',
            '검사유효': 'inspection_validity',
            '검사유효기간': 'inspection_validity',
        }

        for korean_key, field_name in field_mapping.items():
            if korean_key in key:
                info[field_name] = value
                return
