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
            # Content may contain escaped quotes (\') inside HTML <li> elements
            model_matches = re.findall(r"carModel_gubun\('((?:[^'\\]|\\.)*)'\)", html)
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
            # Structure: "2015년 5월<em></em>디젤<em></em>오토<em></em>-<em></em>246,343km"
            # Split by <em> tags to get ordered fields: [year, fuel, transmission, displacement, mileage]
            desc_html = str(car_desc)
            # Remove outer span tags
            inner = re.sub(r'^<span[^>]*>', '', desc_html)
            inner = re.sub(r'</span>$', '', inner)
            # Split by <em></em> or <em/> separators
            parts = re.split(r'<em\s*/?\s*>\s*(?:</em>)?', inner)
            parts = [p.strip() for p in parts if p.strip()]

            # Positional mapping: year, fuel, transmission, displacement, mileage
            if len(parts) >= 1 and '년' in parts[0]:
                year = parts[0]
            if len(parts) >= 2 and parts[1] != '-':
                fuel = parts[1]
            if len(parts) >= 3 and parts[2] != '-':
                transmission = parts[2]
            if len(parts) >= 4 and parts[3] != '-':
                displacement = parts[3]
            if len(parts) >= 5 and parts[4] != '-':
                mileage = parts[4]

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
            # Each <p> has two <span>: first is label, second is value
            # Structure: <p><span>마감시간</span><span class='fc_red'>2026-03-13 12시 30분</span></p>
            info_items = auc_info.find_all('p')
            for p in info_items:
                spans = p.find_all('span')
                if len(spans) >= 2:
                    label = spans[0].get_text(strip=True)
                    value = spans[1].get_text(strip=True)
                    if '마감' in label:
                        deadline = value if value and value != '-' else None
                    elif '입찰' in label or '금액' in label:
                        min_bid = value if value and value != '-' else None
                    elif '보관' in label or '지역' in label:
                        location = value if value and value != '-' else None

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
        """Parse model category strings from JavaScript carModel_gubun() calls.

        The server returns HTML <li> elements with escaped quotes, e.g.:
        <li onclick="searchIns(\\'1\\', \\'기타\\');"><span>기타</span><span>67</span></li>
        """
        categories = []
        try:
            for raw in raw_strings:
                if not raw:
                    continue

                # Unescape \\' → ' so BeautifulSoup can parse the HTML
                unescaped = raw.replace("\\'", "'")

                # Check if it's HTML (contains <li> or <span>)
                if '<' in unescaped and '>' in unescaped:
                    soup = BeautifulSoup(unescaped, 'html.parser')
                    all_lis = soup.find_all('li')
                    if not all_lis:
                        continue

                    for li in all_lis:
                        spans = li.find_all('span')
                        if len(spans) < 2:
                            continue

                        name = spans[0].get_text(strip=True)
                        try:
                            count = int(spans[1].get_text(strip=True))
                        except ValueError:
                            count = 0

                        # Extract search_key from onclick="searchIns('1', '기타')"
                        onclick = li.get('onclick', '')
                        search_key = name
                        search_match = re.search(r"searchIns\([^,]*,\s*'([^']*)'\)", onclick)
                        if search_match:
                            search_key = search_match.group(1)

                        if name:
                            categories.append(HappyCarModelCategory(
                                name=name,
                                count=count,
                                search_key=search_key,
                            ))
                else:
                    # Fallback: pipe-delimited format "name|count"
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
        """Parse the detail page HTML for a single car.

        Page structure (EUC-KR encoded):
        - Images: background-image:url(...) on divs with /nBoard/upload/... paths
        - Sale type: <label class="status2">폐차</label>
        - Reg number: <span> with text "등재번호 : 2026-026458"
        - Specs (detail-info01): <ul><li>label<p>value</p></li></ul>
        - Damage + vehicle info (detail-info03[1]): key:value text block
        - Insurance (detail-info02): raw text with labels
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract idx
            idx = ""
            idx_match = re.search(r'idx=(\d+)', html)
            if idx_match:
                idx = idx_match.group(1)

            # ── Images: background-image URLs with /nBoard/upload/ paths ──
            images = []
            seen = set()
            for div in soup.find_all(style=True):
                style = div.get('style', '')
                m = re.search(r"background-image\s*:\s*url\('?([^'\")\s]+)'?\)", style)
                if m:
                    path = m.group(1)
                    if 'upload' in path and 'no_img' not in path:
                        url = path if path.startswith('http') else f"{self.BASE_URL}{path}"
                        if url not in seen:
                            seen.add(url)
                            images.append(url)

            # ── Sale type from status label ──
            sale_type = ""
            for cls in ['status1', 'status2', 'status3', 'status4', 'status5']:
                label = soup.find('label', class_=cls)
                if label:
                    text = label.get_text(strip=True)
                    if text in ['폐차', '구제', '부품']:
                        sale_type = text
                        break

            # ── Registration number from "등재번호 : XXXX" ──
            registration_number = ""
            for span in soup.find_all('span'):
                text = span.get_text(strip=True)
                m = re.match(r'등재번호\s*:\s*(.+)', text)
                if m:
                    registration_number = m.group(1).strip()
                    break

            # ── Specs from detail-info01: <ul><li>label<p>value</p></li></ul> ──
            specs = {}
            info01 = soup.find(class_='detail-info01')
            if info01:
                for li in info01.find_all('li'):
                    p_tag = li.find('p')
                    if p_tag:
                        # Label is the text node before <p>, value is inside <p>
                        label_text = li.get_text(strip=True).replace(p_tag.get_text(strip=True), '').strip()
                        value_text = p_tag.get_text(strip=True)
                        if label_text and value_text and value_text != '-':
                            self._map_spec_field(specs, label_text, value_text)

            # ── Damage + vehicle info from second detail-info03 ──
            damage_description = None
            vehicle_info = {}
            all_info03 = soup.find_all(class_='detail-info03')
            if len(all_info03) >= 2:
                # Second detail-info03 has damage text + vehicle info as key:value
                damage_block = all_info03[1]
                full_text = damage_block.get_text(separator='\n', strip=True)
                lines = full_text.split('\n')

                # Split into damage text (before key:value pairs) and vehicle info
                damage_lines = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # Check if line is a key:value pair
                    kv_match = re.match(r'^(차량명|차대번호|형식번호|형식년도|최초등록일|색상|주행거리|성능점검유효기간)\s*[:：]\s*(.+)', line)
                    if kv_match:
                        key, value = kv_match.group(1), kv_match.group(2).strip()
                        self._map_vehicle_field(vehicle_info, key, value)
                    else:
                        damage_lines.append(line)

                if damage_lines:
                    damage_description = '\n'.join(damage_lines)

            # ── Insurance history from detail-info02 ──
            insurance = {}
            info02 = soup.find(class_='detail-info02')
            if info02:
                text = info02.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text.split('|') if p.strip()]
                # Parse pairs: label followed by value
                i = 0
                while i < len(parts) - 1:
                    label = parts[i]
                    value = parts[i + 1] if i + 1 < len(parts) else ''
                    if '번호변경' in label:
                        insurance['plate_changes'] = value
                        i += 2
                    elif '소유자변경' in label:
                        insurance['owner_changes'] = value
                        i += 2
                    elif '내차피해' in label:
                        insurance['my_damage'] = value
                        i += 2
                    elif '상대' in label and '피해' in label:
                        insurance['other_damage'] = value
                        i += 2
                    else:
                        i += 1

            # ── Title: from car-desc or vehicle_info ──
            title = vehicle_info.get('car_name_full', '')
            if not title:
                car_desc = soup.find(class_='car-desc')
                if car_desc:
                    # car-desc has specs, not title — get from hidden input or meta
                    pass
            # Try hidden input price (indicates we're on detail page)
            if not title:
                # Extract from first h2 before detail-info03
                for h2 in soup.find_all('h2', class_='title'):
                    h2_text = h2.get_text(strip=True)
                    if '차량 상세정보' in h2_text or '보험이력' in h2_text or '유의사항' in h2_text:
                        continue
                    title = h2_text
                    break

            detail = HappyCarDetail(
                idx=idx,
                title=title,
                registration_number=registration_number,
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

            logger.info(f"✅ Parsed car detail for idx={idx}, title={title}, images={len(images)}")
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
            '등록연식': 'year',
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
            '최소입찰금액': 'min_bid',
            '최저입찰가': 'min_bid',
            '최저가': 'min_bid',
            '입찰가': 'min_bid',
            '보관장소': 'location',
            '보관지': 'location',
            '위치': 'location',
            '경매종료일시': 'deadline',
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
            '차량명': 'car_name_full',
            '차명': 'car_name_full',
            '신차가격': 'msrp',
            '신차가': 'msrp',
            '차대번호': 'vin',
            'VIN': 'vin',
            '형식번호': 'form_number',
            '형식년도': 'form_year',
            '최초등록일': 'first_registration',
            '최초등록': 'first_registration',
            '색상': 'color',
            '주행거리': 'actual_mileage',
            '실주행': 'actual_mileage',
            '실주행거리': 'actual_mileage',
            '성능점검유효기간': 'inspection_validity',
            '검사유효': 'inspection_validity',
            '검사유효기간': 'inspection_validity',
        }

        for korean_key, field_name in field_mapping.items():
            if korean_key in key:
                info[field_name] = value
                return
