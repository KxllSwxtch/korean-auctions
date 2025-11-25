"""
SK Auction Parser

Parses JSON API responses and HTML pages from SK Car Rental Auction.
URL: https://auction.skcarrental.com
"""

import re
from typing import List, Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
from loguru import logger
from datetime import datetime

from app.parsers.base_auction_parser import BaseAuctionParser
from app.models.sk_auction import (
    SKAuctionCar,
    SKAuctionCarDetail,
    SKAuctionBrand,
    SKAuctionModel,
    SKAuctionGeneration,
    SKAuctionFuelTypeOption,
    SKAuctionYearOption,
    SKAuctionResponse,
    SKAuctionPaginationInfo,
    SKAuctionCarOwner,
    SKAuctionCarSpecs,
    SKAuctionConditionCheck,
    SKAuctionLegalStatus,
    SKAuctionMedia,
    SKAuctionInspectionRecord,
    SKAuctionTireInfo,
)


class SKAuctionParser(BaseAuctionParser):
    """Parser for SK Auction data"""

    # Image base URL
    IMAGE_BASE_URL = "https://aucmark.skcarrental.com/uploadFiles/AU_CAR_IMG_ORG"

    # Selector fallbacks for HTML parsing
    SELECTOR_FALLBACKS = {
        "auction_num": [
            ("div", "auction-num", None),
        ],
        "product_title": [
            ("div", "product-title", None),
        ],
        "resource_box": [
            ("div", "resource-box", None),
        ],
        "price_box": [
            ("div", "price-box", None),
        ],
        "parking_span": [
            ("span", "parking", None),
        ],
        "auction_status": [
            ("div", "impact", None),
        ],
        "car_number_row": [
            ("li", None, "차량번호"),
        ],
        "auction_date_row": [
            ("li", None, "경매일자"),
        ],
        "detail_specs": [
            ("ul", "ul_list type-carinfo", None),
            ("ul", "ul_list", None),
        ],
        "condition_check": [
            ("ul", "ul-repaircheck type2", None),
        ],
        "special_notes": [
            ("div", "comment", None),
        ],
    }

    def __init__(self):
        super().__init__("SK Auction Parser")

    def parse(self, *args, **kwargs) -> Any:
        """Main parse entry point - dispatches to specific parsers"""
        raise NotImplementedError("Use specific parse methods instead")

    # ==================== JSON Parsing Methods ====================

    def parse_cars_json(
        self,
        json_data: Dict[str, Any],
        page: int = 1,
        page_size: int = 20
    ) -> SKAuctionResponse:
        """
        Parse car listings from SK Auction JSON API response.

        Args:
            json_data: Raw JSON response from selectExhiList.do
            page: Current page number
            page_size: Records per page

        Returns:
            SKAuctionResponse with parsed cars
        """
        self._reset_stats()
        cars: List[SKAuctionCar] = []

        try:
            # Parse pagination info
            pagination_info = json_data.get("paginationInfo", {})
            pagination = SKAuctionPaginationInfo(
                current_page=pagination_info.get("currentPageNo", page),
                records_per_page=pagination_info.get("recordCountPerPage", page_size),
                page_size=pagination_info.get("pageSize", 10),
                total_records=pagination_info.get("totalRecordCount", 0),
                total_pages=pagination_info.get("totalPageCount", 0),
                first_page=pagination_info.get("firstPageNo", 1),
                last_page=pagination_info.get("lastPageNo", 1),
            )

            # Parse result list
            result_list = json_data.get("resultList", [])
            logger.info(f"📋 Parsing {len(result_list)} cars from SK Auction")

            for item in result_list:
                try:
                    car = self._parse_single_car_json(item)
                    if car:
                        cars.append(car)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse car: {e}")
                    continue

            self._track_extraction("cars_list", len(cars) > 0)

            # Get auction date from search data
            search_data = json_data.get("searchData", {})
            auction_date = search_data.get("auctDt", "")

            return SKAuctionResponse(
                success=True,
                message=f"Successfully parsed {len(cars)} cars",
                cars=cars,
                pagination=pagination,
                total_count=pagination.total_records,
                current_page=pagination.current_page,
                page_size=pagination.records_per_page,
                total_pages=pagination.total_pages,
                has_next_page=pagination.current_page < pagination.total_pages,
                has_prev_page=pagination.current_page > 1,
                auction_date=auction_date,
            )

        except Exception as e:
            logger.error(f"❌ SK Auction Parser: Failed to parse cars JSON: {e}")
            return SKAuctionResponse(
                success=False,
                message=f"Failed to parse cars: {str(e)}",
                cars=[],
            )

    def _parse_single_car_json(self, item: Dict[str, Any]) -> Optional[SKAuctionCar]:
        """Parse a single car from JSON item"""
        try:
            # Extract basic fields
            car_no = item.get("carNo", "")
            mng_no = item.get("mngNo", "")
            mng_div_cd = item.get("mngDivCd", "")
            exhi_regi_seq = item.get("exhiRegiSeq", 1)

            # Starting price is in units of 10,000 won
            starting_price = item.get("strtAmt", 0)
            starting_price_won = starting_price * 10000

            # Construct image URL
            # Pattern: https://aucmark.skcarrental.com/uploadFiles/AU_CAR_IMG_ORG/{folder}/{mng_no}21.JPG/watermark/type1
            folder = mng_no[2:8] if len(mng_no) > 8 else "000001"
            main_image_url = f"{self.IMAGE_BASE_URL}/{folder}/{mng_no}21.JPG/watermark/type1"

            car = SKAuctionCar(
                # Identification
                car_no=car_no,
                mng_no=mng_no,
                mng_div_cd=mng_div_cd,
                exhi_regi_seq=exhi_regi_seq,
                # Auction info
                exhi_no=item.get("exhiNo", ""),
                auction_date=item.get("auctDt", ""),
                lane_div=item.get("laneDiv", ""),
                exhi_div_cd=item.get("exhiDivCd", "01"),
                exhi_stat_cd=item.get("exhiStatCd", "02"),
                exhi_regi_stat_cd=item.get("exhiRegiStatCd", "02"),
                # Vehicle codes
                mdl_cd=item.get("mdlCd", ""),
                car_grp_cd=item.get("carGrpCd", ""),
                # Vehicle names
                car_name=item.get("carCdNm", ""),
                model_name=item.get("mdlCdNm", ""),
                generation_name=item.get("carGrpCdNm", ""),
                # Technical specs
                year=int(item.get("regiYyyy", 0)),
                mileage=item.get("km", 0),
                transmission=item.get("trnsCdNm", ""),
                transmission_code=item.get("trnsCd", "01"),
                fuel_type=item.get("fuelCdNm", ""),
                color=item.get("colorCdNm", ""),
                color_code=item.get("colorCd", ""),
                # Condition
                accident_grade=item.get("accdScoreCdNm", item.get("accdScoreCd", "")),
                exterior_grade=item.get("outScoreCdNm", item.get("outScoreCd", "")),
                # Pricing
                starting_price=starting_price,
                starting_price_won=starting_price_won,
                # Location
                parking_location=item.get("pkltNoNm", ""),
                # Stats
                view_count=item.get("viewCnt", 0),
                row_number=item.get("no", 0),
                # Watchlist
                concern_yn=item.get("consYn"),
                concern_search_mode=item.get("concSearchMode", "none"),
                # Status names
                exhi_div_name=item.get("exhiDivCdNm", ""),
                exhi_stat_name=item.get("exhiStatCdNm", ""),
                exhi_regi_stat_name=item.get("exhiRegiStatCdNm", ""),
                # Image
                main_image_url=main_image_url,
            )

            return car

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse car item: {e}")
            return None

    def parse_brands_json(self, json_data: Dict[str, Any]) -> List[SKAuctionBrand]:
        """Parse brands list from API response"""
        brands: List[SKAuctionBrand] = []

        try:
            result_list = json_data.get("result", [])
            logger.info(f"📋 Parsing {len(result_list)} brands from SK Auction")

            for item in result_list:
                brand = SKAuctionBrand(
                    code=item.get("code", ""),
                    name=item.get("name", ""),
                    exhi_count=item.get("exhiCnt", 0),
                    doim_cd=item.get("doimCd"),
                    disp_order=item.get("dispOrdr"),
                )
                brands.append(brand)

            logger.info(f"✅ Parsed {len(brands)} brands")
            return brands

        except Exception as e:
            logger.error(f"❌ Failed to parse brands: {e}")
            return []

    def parse_models_json(
        self,
        json_data: Dict[str, Any],
        brand_code: str
    ) -> List[SKAuctionModel]:
        """Parse models list from API response"""
        models: List[SKAuctionModel] = []

        try:
            result_list = json_data.get("result", [])
            logger.info(f"📋 Parsing {len(result_list)} models for brand {brand_code}")

            for item in result_list:
                model = SKAuctionModel(
                    code=item.get("code", ""),
                    name=item.get("name", ""),
                    brand_code=item.get("mkrCd", brand_code),
                    exhi_count=item.get("exhiCnt", 0),
                )
                models.append(model)

            logger.info(f"✅ Parsed {len(models)} models")
            return models

        except Exception as e:
            logger.error(f"❌ Failed to parse models: {e}")
            return []

    def parse_generations_json(
        self,
        json_data: Dict[str, Any],
        model_code: str
    ) -> List[SKAuctionGeneration]:
        """Parse generations list from API response"""
        generations: List[SKAuctionGeneration] = []

        try:
            result_list = json_data.get("result", [])
            logger.info(f"📋 Parsing {len(result_list)} generations for model {model_code}")

            for item in result_list:
                generation = SKAuctionGeneration(
                    code=item.get("code", ""),
                    name=item.get("name", ""),
                    brand_code=item.get("mkrCd", ""),
                    exhi_count=item.get("exhiCnt", 0),
                )
                generations.append(generation)

            logger.info(f"✅ Parsed {len(generations)} generations")
            return generations

        except Exception as e:
            logger.error(f"❌ Failed to parse generations: {e}")
            return []

    def parse_fuel_types_json(self, json_data: Dict[str, Any]) -> List[SKAuctionFuelTypeOption]:
        """Parse fuel types list from API response"""
        fuel_types: List[SKAuctionFuelTypeOption] = []

        try:
            result_list = json_data.get("result", [])

            for item in result_list:
                # Skip empty "all" option
                code = item.get("code", "")
                if code:
                    fuel_type = SKAuctionFuelTypeOption(
                        code=code,
                        name=item.get("name", ""),
                    )
                    fuel_types.append(fuel_type)

            logger.info(f"✅ Parsed {len(fuel_types)} fuel types")
            return fuel_types

        except Exception as e:
            logger.error(f"❌ Failed to parse fuel types: {e}")
            return []

    def parse_years_json(self, json_data: Dict[str, Any]) -> List[SKAuctionYearOption]:
        """Parse years list from API response"""
        years: List[SKAuctionYearOption] = []

        try:
            result_list = json_data.get("result", [])

            for item in result_list:
                code = item.get("code", "")
                if code:
                    year = SKAuctionYearOption(
                        code=code,
                        name=item.get("name", ""),
                    )
                    years.append(year)

            logger.info(f"✅ Parsed {len(years)} years")
            return years

        except Exception as e:
            logger.error(f"❌ Failed to parse years: {e}")
            return []

    # ==================== HTML Parsing Methods ====================

    def parse_car_detail_html(
        self,
        html: str,
        mng_div_cd: str,
        mng_no: str,
        exhi_regi_seq: int
    ) -> Optional[SKAuctionCarDetail]:
        """
        Parse car detail page HTML from SK Auction.

        Args:
            html: Raw HTML content
            mng_div_cd: Management division code (e.g., SR)
            mng_no: Management number (e.g., SR25000114199)
            exhi_regi_seq: Exhibition registration sequence

        Returns:
            SKAuctionCarDetail or None if parsing failed
        """
        self._reset_stats()

        try:
            soup = BeautifulSoup(html, "lxml")

            # Parse basic info
            basic_info = self._parse_basic_info(soup)
            self._track_extraction("basic_info", basic_info.get("car_name"))

            # Parse owner info
            owner_info = self._parse_owner_info(soup)
            self._track_extraction("owner_info", owner_info.company_name)

            # Parse technical specs
            technical_specs = self._parse_technical_specs(soup)
            self._track_extraction("technical_specs", technical_specs.year)

            # Parse condition check
            condition_check = self._parse_condition_check(soup)
            self._track_extraction("condition_check", condition_check.overall_score)

            # Parse legal status
            legal_status = self._parse_legal_status(soup)
            self._track_extraction("legal_status", True)

            # Parse media
            media = self._parse_media(soup, mng_no)
            self._track_extraction("media", len(media.main_images) > 0)

            # Parse inspection record
            inspection_record = self._parse_inspection_record(soup)
            self._track_extraction("inspection_record", inspection_record.record_number)

            # Parse tire info
            tire_info = self._parse_tire_info(soup)

            # Extract car number
            car_no = self._extract_car_number(soup)
            self._track_extraction("car_no", car_no)

            # Build car detail
            car_detail = SKAuctionCarDetail(
                car_no=car_no or "",
                mng_no=mng_no,
                mng_div_cd=mng_div_cd,
                exhi_regi_seq=exhi_regi_seq,
                exhi_no=basic_info.get("exhi_no", ""),
                auction_date=basic_info.get("auction_date"),
                lane_div=basic_info.get("lane_div"),
                auction_status=basic_info.get("auction_status"),
                auction_result=basic_info.get("auction_result"),
                parking_location=basic_info.get("parking_location"),
                car_name=basic_info.get("car_name", ""),
                starting_price=basic_info.get("starting_price", 0),
                starting_price_text=basic_info.get("starting_price_text"),
                owner_info=owner_info,
                technical_specs=technical_specs,
                condition_check=condition_check,
                legal_status=legal_status,
                tire_info=tire_info,
                media=media,
                inspection_record=inspection_record,
                parsed_at=datetime.now(),
                source_url=f"https://auction.skcarrental.com/pc/No/{mng_div_cd}/{mng_no}/{exhi_regi_seq}",
            )

            # Log extraction summary
            summary = self._get_extraction_summary()
            logger.info(
                f"✅ SK Auction detail parsed: {summary['extracted_count']}/{summary['total_fields']} fields "
                f"({summary['success_rate']:.1f}%)"
            )

            return car_detail

        except Exception as e:
            logger.error(f"❌ Failed to parse SK Auction car detail HTML: {e}")
            self._save_debug_html(html, mng_no, "parsing_failed")
            return None

    def _parse_basic_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parse basic info from car detail page"""
        info: Dict[str, Any] = {}

        try:
            # Exhibition number
            auction_num = self._find_with_fallbacks(soup, "auction_num")
            if auction_num:
                text = auction_num.get_text(strip=True)
                match = re.search(r"(\d+)", text)
                if match:
                    info["exhi_no"] = match.group(1)

            # Product title (car name)
            product_title = self._find_with_fallbacks(soup, "product_title")
            if product_title:
                info["car_name"] = product_title.get_text(strip=True)

            # Resource box (year, mileage, color, transmission)
            resource_box = self._find_with_fallbacks(soup, "resource_box")
            if resource_box:
                spans = resource_box.find_all("span")
                for i, span in enumerate(spans):
                    text = span.get_text(strip=True)
                    if i == 0 and "년식" in text:
                        info["year"] = text.replace("년식", "").strip()
                    elif i == 1 and "km" in text.lower():
                        info["mileage"] = text
                    elif i == 2:
                        info["color"] = text
                    elif i == 3:
                        info["transmission"] = text

            # Lane and parking
            bdg_box = soup.find("div", class_="bdg-box type01")
            if bdg_box:
                spans = bdg_box.find_all("span")
                for span in spans:
                    text = span.get_text(strip=True)
                    if "레인" in text:
                        info["lane_div"] = text.replace("레인", "").strip()
                    elif "parking" in span.get("class", []) or "주차면" in text:
                        info["parking_location"] = text.replace("주차면", "").strip()

            # Price
            price_box = self._find_with_fallbacks(soup, "price_box")
            if price_box:
                price_span = price_box.find("span", class_="commaFmt")
                if price_span:
                    price_text = price_span.get_text(strip=True)
                    info["starting_price_text"] = price_text
                    # Extract number (e.g., "1,140만원" -> 1140)
                    match = re.search(r"([\d,]+)", price_text)
                    if match:
                        price_str = match.group(1).replace(",", "")
                        info["starting_price"] = int(price_str)

            # Auction status
            status_div = soup.find("div", class_="impact")
            if status_div:
                info["auction_status"] = status_div.get_text(strip=True)

            # Auction date
            inner_box = soup.find("div", class_="inner-box")
            if inner_box:
                li_items = inner_box.find_all("li")
                for li in li_items:
                    span = li.find("span")
                    if span and "경매일자" in span.get_text():
                        div = li.find("div")
                        if div:
                            info["auction_date"] = div.get_text(strip=True)

            # Auction result
            result_box = soup.find("li", string=lambda s: s and "경매결과" in s)
            if result_box:
                div = result_box.find("div", class_="impact")
                if div:
                    info["auction_result"] = div.get_text(strip=True)

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse basic info: {e}")

        return info

    def _parse_owner_info(self, soup: BeautifulSoup) -> SKAuctionCarOwner:
        """Parse owner information"""
        owner = SKAuctionCarOwner()

        try:
            # Find owner section
            owner_section = soup.find("h5", string="소유자")
            if owner_section:
                info_box = owner_section.find_next("div", class_="inner-box bg")
                if info_box:
                    li_items = info_box.find_all("li")
                    for li in li_items:
                        span = li.find("span")
                        div = li.find("div")
                        if span and div:
                            label = span.get_text(strip=True)
                            value = div.get_text(strip=True)
                            if "상호" in label:
                                owner.company_name = value
                            elif "성명" in label:
                                owner.representative_name = value
                            elif "주민등록번호" in label:
                                owner.registration_number = value
                            elif "주소" in label:
                                owner.address = value

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse owner info: {e}")

        return owner

    def _parse_technical_specs(self, soup: BeautifulSoup) -> SKAuctionCarSpecs:
        """Parse technical specifications"""
        specs = SKAuctionCarSpecs()

        try:
            # Find specs section (차량 상세정보)
            specs_section = soup.find("h3", string="차량 상세정보")
            if specs_section:
                parent_div = specs_section.find_parent("div", class_="detail-box")
                if parent_div:
                    inner_box = parent_div.find("div", class_="inner-box")
                    if inner_box:
                        li_items = inner_box.find_all("li")
                        for li in li_items:
                            span = li.find("span")
                            div = li.find("div")
                            if span and div:
                                label = span.get_text(strip=True)
                                value = div.get_text(strip=True)

                                if label == "연식":
                                    specs.year = value
                                elif label == "주행거리":
                                    specs.mileage = value
                                elif label == "최초등록일":
                                    specs.first_registration_date = value
                                elif label == "변속기":
                                    specs.transmission = value
                                elif "용도" in label:
                                    specs.usage_type = value
                                elif label == "색상":
                                    specs.color = value
                                elif "원동기" in label:
                                    specs.engine_type = value
                                elif label == "연료":
                                    specs.fuel_type = value
                                elif "검사유효" in label:
                                    specs.inspection_valid_until = value
                                elif label == "배기량":
                                    specs.displacement = value
                                elif label == "차종":
                                    specs.car_type = value
                                elif "승차정원" in label:
                                    specs.seating_capacity = value
                                elif "주요옵션" in label:
                                    specs.main_options = value
                                elif "특이사항" in label:
                                    specs.special_notes = value
                                elif "완비서류" in label:
                                    specs.complete_documents = value
                                elif "보관품" in label:
                                    specs.stored_items = value

            # Find VIN from inspection record
            car_info_section = soup.find("h5", string="자동차의 표시")
            if car_info_section:
                info_box = car_info_section.find_next("div", class_="inner-box bg")
                if info_box:
                    li_items = info_box.find_all("li")
                    for li in li_items:
                        span = li.find("span")
                        div = li.find("div")
                        if span and div:
                            label = span.get_text(strip=True)
                            value = div.get_text(strip=True)
                            if "차대번호" in label:
                                specs.vin_number = value

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse technical specs: {e}")

        return specs

    def _parse_condition_check(self, soup: BeautifulSoup) -> SKAuctionConditionCheck:
        """Parse condition check results"""
        condition = SKAuctionConditionCheck()

        try:
            # Find condition check section
            condition_section = soup.find("h3", string="상태점검표")
            if condition_section:
                parent_div = condition_section.find_parent("div", class_="detail-box")
                if parent_div:
                    check_list = parent_div.find("ul", class_="ul-repaircheck type2")
                    if check_list:
                        li_items = check_list.find_all("li")
                        for li in li_items:
                            span = li.find("span")
                            div = li.find("div")
                            if span and div:
                                label = span.get_text(strip=True)
                                value = div.get_text(strip=True)

                                if label == "평가점":
                                    condition.overall_score = value
                                elif label == "엔진":
                                    condition.engine_condition = value
                                elif label == "미션":
                                    condition.transmission_condition = value
                                elif label == "제동":
                                    condition.brake_condition = value
                                elif "동력전달" in label:
                                    condition.power_transmission = value
                                elif label == "공조":
                                    condition.air_conditioning = value
                                elif label == "조향":
                                    condition.steering_condition = value
                                elif label == "전기":
                                    condition.electrical_condition = value
                                elif label == "실내":
                                    condition.interior_condition = value

                    # Special notes
                    comment_div = parent_div.find("div", class_="comment")
                    if comment_div:
                        condition.special_notes = comment_div.get_text(strip=True)

                    # Status map image
                    img_div = parent_div.find("div", class_="img")
                    if img_div:
                        img = img_div.find("img")
                        if img and img.get("src"):
                            src = img.get("src")
                            if not src.startswith("http"):
                                src = f"https://auction.skcarrental.com{src}"
                            condition.status_map_image = src

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse condition check: {e}")

        return condition

    def _parse_legal_status(self, soup: BeautifulSoup) -> SKAuctionLegalStatus:
        """Parse legal status (seizure/mortgage)"""
        status = SKAuctionLegalStatus()

        try:
            # Find legal status section
            judang_list = soup.find("ul", class_="ul-repaircheck hori judang")
            if judang_list:
                li_items = judang_list.find_all("li")
                for li in li_items:
                    span = li.find("span")
                    div = li.find("div")
                    if span and div:
                        label = span.get_text(strip=True)
                        # Extract number from div
                        text = div.get_text(strip=True)
                        match = re.search(r"(\d+)", text)
                        count = int(match.group(1)) if match else 0

                        if "압류" in label:
                            status.seizure_count = count
                        elif "저당" in label:
                            status.mortgage_count = count
                        elif "구변" in label:
                            status.modification_count = count

            # Last inquiry date
            inquiry_text = soup.find(string=re.compile(r"최종조회일자"))
            if inquiry_text:
                match = re.search(r"(\d{4}\.\d{2}\.\d{2})", inquiry_text)
                if match:
                    status.last_inquiry_date = match.group(1)

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse legal status: {e}")

        return status

    def _parse_media(self, soup: BeautifulSoup, mng_no: str) -> SKAuctionMedia:
        """Parse media files"""
        media = SKAuctionMedia()

        try:
            # Parse main images from swiper
            swiper = soup.find("p", class_="topSwiper")
            if swiper:
                slides = swiper.find_all("span", class_="swiper-slide")
                seen_urls = set()
                for slide in slides:
                    # Skip duplicate slides
                    if "swiper-slide-duplicate" in slide.get("class", []):
                        continue
                    img = slide.find("img")
                    if img and img.get("src"):
                        url = img.get("src")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            media.main_images.append(url)

            # Parse thumbnail images
            thumb_swiper = soup.find("p", class_="thumbnailSwiper")
            if thumb_swiper:
                slides = thumb_swiper.find_all("span", class_="swiper-slide")
                seen_urls = set()
                for slide in slides:
                    if "swiper-slide-duplicate" in slide.get("class", []):
                        continue
                    img = slide.find("img")
                    if img and img.get("src"):
                        url = img.get("src")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            media.thumbnail_images.append(url)

            # Parse undercarriage image
            bottom_img = soup.find("div", class_="bottomimg")
            if bottom_img:
                img = bottom_img.find("img")
                if img and img.get("src"):
                    media.undercarriage_image = img.get("src")

            # Parse undercarriage videos
            video_li = soup.find_all("li", class_="fuc-imediabig")
            for li in video_li:
                obj = li.find("object")
                if obj and obj.get("data"):
                    media.undercarriage_videos.append(obj.get("data"))

            # Parse CV joint images
            tire_section = soup.find("div", class_="tabwrap2")
            if tire_section:
                img_divs = tire_section.find_all("div", class_="img fuc-imgbig")
                for div in img_divs:
                    img = div.find("img")
                    if img and img.get("src"):
                        media.cv_joint_images.append(img.get("src"))

            logger.debug(
                f"📷 Parsed media: {len(media.main_images)} images, "
                f"{len(media.undercarriage_videos)} videos"
            )

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse media: {e}")

        return media

    def _parse_inspection_record(self, soup: BeautifulSoup) -> SKAuctionInspectionRecord:
        """Parse inspection record"""
        record = SKAuctionInspectionRecord()

        try:
            # Find inspection record section
            record_section = soup.find("h3", string=re.compile(r"점검.*기록부"))
            if record_section:
                # Record number
                record_no = record_section.find("i", class_="carrepair-no")
                if record_no:
                    text = record_no.get_text(strip=True)
                    match = re.search(r"제\s*(\d+)\s*호", text)
                    if match:
                        record.record_number = match.group(1)

            # Footer info
            footer = soup.find("div", class_="footer-info")
            if footer:
                # Date
                date_i = footer.find("i")
                if date_i:
                    record.inspection_date = date_i.get_text(strip=True)
                # Location and inspector
                em = footer.find("em")
                if em:
                    text = em.get_text(strip=True)
                    parts = text.split("\n") if "\n" in text else [text]
                    if len(parts) >= 1:
                        record.inspector_location = parts[0].strip()
                    if len(parts) >= 2:
                        record.inspector_name = parts[1].strip()

            # Identity checks
            identity_section = soup.find("span", string="동일성확인")
            if identity_section:
                parent_li = identity_section.find_parent("li")
                if parent_li:
                    vin_radio = parent_li.find("input", value="Y")
                    if vin_radio and vin_radio.get("checked") is not None:
                        record.identity_check_vin = True
                    engine_radio = parent_li.find("input", value="N")
                    if engine_radio and engine_radio.get("checked") is not None:
                        record.identity_check_engine = True

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse inspection record: {e}")

        return record

    def _parse_tire_info(self, soup: BeautifulSoup) -> Optional[SKAuctionTireInfo]:
        """Parse tire condition information"""
        try:
            tire_section = soup.find("div", class_="tabwrap3")
            if not tire_section:
                return None

            tire_info = SKAuctionTireInfo()
            tire_states = tire_section.find_all("li")

            for li in tire_states:
                title_b = li.find("b")
                if not title_b:
                    continue

                title = title_b.get_text(strip=True)
                tire_div = li.find("div", class_="tire-img")
                state_div = li.find("div", class_="state")

                if tire_div:
                    spans = tire_div.find_all("span")
                    values = [s.get_text(strip=True) for s in spans]
                    state = state_div.get_text(strip=True) if state_div else ""

                    tire_data = {
                        "left": values[0] if len(values) > 0 else "",
                        "center": values[1] if len(values) > 1 else "",
                        "right": values[2] if len(values) > 2 else "",
                        "state": state,
                    }

                    if "운전석 앞" in title:
                        tire_info.front_left = tire_data
                    elif "보조석 앞" in title or "조수석 앞" in title:
                        tire_info.front_right = tire_data
                    elif "운전석 뒤" in title:
                        tire_info.rear_left = tire_data
                    elif "보조석 뒤" in title or "조수석 뒤" in title:
                        tire_info.rear_right = tire_data

            return tire_info

        except Exception as e:
            logger.warning(f"⚠️ Failed to parse tire info: {e}")
            return None

    def _extract_car_number(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract car registration number"""
        try:
            # Try from inner-box
            car_no_li = soup.find("li", string=lambda s: s and "차량번호" in str(s))
            if car_no_li:
                div = car_no_li.find("div")
                if div:
                    return div.get_text(strip=True).split("\n")[0].strip()

            # Try from hidden div
            hidden_div = soup.find("div", id="hdn_carNo")
            if hidden_div:
                return hidden_div.get_text(strip=True)

        except Exception as e:
            logger.warning(f"⚠️ Failed to extract car number: {e}")

        return None
