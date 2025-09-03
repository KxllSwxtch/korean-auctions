"""
HeyDealer Accident Diagram Scraper
Scrapes actual damage data from HeyDealer car detail pages
"""

import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
import re
import json

logger = logging.getLogger(__name__)


class HeyDealerAccidentScraper:
    """Scraper for HeyDealer accident damage information"""
    
    def __init__(self, cookies: Dict, headers: Dict):
        self.cookies = cookies
        self.headers = headers
        self.base_url = "https://dealer.heydealer.com"
        
    def get_car_detail_html(self, car_id: str) -> Optional[str]:
        """Get the HTML content of a car detail page"""
        try:
            url = f"{self.base_url}/cars/{car_id}/"
            response = requests.get(url, cookies=self.cookies, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"Failed to get car detail page: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching car detail page: {e}")
            return None
            
    def parse_accident_data_from_html(self, html: str) -> Dict[str, Any]:
        """Parse accident damage data from the car detail HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for the accident repair section
            accident_sections = [
                soup.find('div', class_=re.compile(r'accidentRepair')),
                soup.find('div', class_=re.compile(r'carsAccidentRepair')),
                soup.find('div', class_=re.compile(r'accident.*repair', re.I)),
            ]
            
            accident_section = None
            for section in accident_sections:
                if section:
                    accident_section = section
                    break
                    
            if not accident_section:
                logger.warning("No accident section found in HTML")
                return self._get_empty_response()
                
            # Find all damage markers (buttons with damage classes)
            damage_markers = []
            
            # Look for buttons with weld, painted, or exchange classes
            damage_buttons = accident_section.find_all('button', class_=re.compile(r'(weld|painted|exchange)'))
            
            for button in damage_buttons:
                # Extract position from style attribute
                style = button.get('style', '')
                position_match = re.search(r'translate\((\d+)px,\s*(\d+)px\)', style)
                
                if position_match:
                    x = int(position_match.group(1))
                    y = int(position_match.group(2))
                    
                    # Determine repair type from class
                    classes = button.get('class', [])
                    if isinstance(classes, str):
                        classes = classes.split()
                        
                    repair_type = 'none'
                    if any('weld' in cls for cls in classes):
                        repair_type = 'weld'
                    elif any('painted' in cls for cls in classes):
                        repair_type = 'painted'
                    elif any('exchange' in cls for cls in classes):
                        repair_type = 'exchange'
                        
                    damage_markers.append({
                        'position': [x, y],
                        'repair': repair_type
                    })
                    
            # Also look for animation divs which might contain damage info
            damage_divs = accident_section.find_all('div', class_=re.compile(r'accidentRepairAnimation'))
            
            for div in damage_divs:
                # Check style for position
                style = div.get('style', '')
                position_match = re.search(r'left:\s*(\d+)px;?\s*top:\s*(\d+)px', style)
                
                if position_match:
                    x = int(position_match.group(1))
                    y = int(position_match.group(2))
                    
                    # Look for nested button to determine type
                    inner_button = div.find('div', class_=re.compile(r'accidentRepairButton'))
                    if inner_button:
                        classes = inner_button.get('class', [])
                        if isinstance(classes, str):
                            classes = classes.split()
                            
                        repair_type = 'none'
                        if any('weld' in cls for cls in classes):
                            repair_type = 'weld'
                        elif any('painted' in cls for cls in classes):
                            repair_type = 'painted'
                        elif any('exchange' in cls for cls in classes):
                            repair_type = 'exchange'
                            
                        damage_markers.append({
                            'position': [x, y],
                            'repair': repair_type
                        })
                        
            logger.info(f"Found {len(damage_markers)} damage markers in HTML")
            return {
                'damage_markers': damage_markers,
                'has_damages': len(damage_markers) > 0
            }
            
        except Exception as e:
            logger.error(f"Error parsing accident data from HTML: {e}")
            return self._get_empty_response()
            
    def _get_empty_response(self) -> Dict[str, Any]:
        """Return empty response structure"""
        return {
            'damage_markers': [],
            'has_damages': False
        }
        
    def merge_with_api_data(self, api_data: Dict, scraped_data: Dict) -> Dict:
        """
        Merge scraped damage data with API template data
        Updates the repair status based on scraped positions
        """
        try:
            if not scraped_data.get('has_damages'):
                return api_data
                
            damage_markers = scraped_data.get('damage_markers', [])
            accident_repairs = api_data.get('accident_repairs', [])
            
            # Create a map of positions to repair types from scraped data
            damage_map = {}
            for marker in damage_markers:
                pos_key = f"{marker['position'][0]}_{marker['position'][1]}"
                damage_map[pos_key] = marker['repair']
                
            # Update accident_repairs based on position matching
            for repair in accident_repairs:
                if 'position' in repair:
                    # Try exact match first
                    pos_key = f"{repair['position'][0]}_{repair['position'][1]}"
                    if pos_key in damage_map:
                        repair['repair'] = damage_map[pos_key]
                        repair['repair_display'] = self._get_repair_display(damage_map[pos_key])
                    else:
                        # Try fuzzy match (within 10 pixels)
                        for marker in damage_markers:
                            if (abs(repair['position'][0] - marker['position'][0]) < 10 and 
                                abs(repair['position'][1] - marker['position'][1]) < 10):
                                repair['repair'] = marker['repair']
                                repair['repair_display'] = self._get_repair_display(marker['repair'])
                                break
                                
            # Recalculate damage summary
            damage_summary = {
                'exchange': 0,
                'weld': 0,
                'painted': 0,
                'none': 0
            }
            
            for repair in accident_repairs:
                repair_type = repair.get('repair', 'none')
                if repair_type in damage_summary:
                    damage_summary[repair_type] += 1
                    
            api_data['damage_summary'] = damage_summary
            api_data['total_damages'] = damage_summary['exchange'] + damage_summary['weld'] + damage_summary['painted']
            
            return api_data
            
        except Exception as e:
            logger.error(f"Error merging data: {e}")
            return api_data
            
    def _get_repair_display(self, repair_type: str) -> str:
        """Get display text for repair type"""
        displays = {
            'weld': '용접 (Welded)',
            'painted': '도색 (Painted)',
            'exchange': '교환 (Exchanged)',
            'none': '없음 (None)'
        }
        return displays.get(repair_type, repair_type)


def scrape_and_merge_accident_data(car_id: str, cookies: Dict, headers: Dict, api_data: Dict) -> Dict:
    """
    Main function to scrape and merge accident data
    
    Args:
        car_id: The car ID
        cookies: Auth cookies
        headers: Request headers
        api_data: The base API response data
        
    Returns:
        Merged data with actual damage information
    """
    try:
        scraper = HeyDealerAccidentScraper(cookies, headers)
        
        # Get the car detail HTML
        html = scraper.get_car_detail_html(car_id)
        if not html:
            logger.warning(f"Could not get HTML for car {car_id}")
            return api_data
            
        # Parse damage data from HTML
        scraped_data = scraper.parse_accident_data_from_html(html)
        
        # Merge with API data
        merged_data = scraper.merge_with_api_data(api_data, scraped_data)
        
        logger.info(f"Successfully scraped and merged data for car {car_id}")
        return merged_data
        
    except Exception as e:
        logger.error(f"Error in scrape_and_merge_accident_data: {e}")
        return api_data