#!/usr/bin/env python3
"""
Script to extract carList data from SSANCAR website
This will generate the ssancar_carlist.json file needed for models filtering
"""

import json
import re
import requests
from bs4 import BeautifulSoup
from loguru import logger

def extract_carlist_from_ssancar():
    """Extract carList data from SSANCAR website"""
    try:
        logger.info("🔍 Fetching SSANCAR main page...")
        
        # Fetch the main page
        response = requests.get(
            "https://www.ssancar.com/",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
            timeout=30
        )
        response.raise_for_status()
        
        logger.info("✅ Page fetched successfully")
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the script tag containing carList
        carlist_pattern = re.compile(r'var\s+carList\s*=\s*({[^;]+});', re.DOTALL)
        script_tags = soup.find_all('script', text=carlist_pattern)
        
        if not script_tags:
            logger.error("❌ Could not find carList in page")
            return None
            
        # Extract carList from script
        script_content = script_tags[0].string
        match = carlist_pattern.search(script_content)
        
        if not match:
            logger.error("❌ Could not extract carList data")
            return None
            
        carlist_str = match.group(1)
        
        # Clean up the JavaScript object to make it valid JSON
        # Replace single quotes with double quotes
        carlist_str = re.sub(r"'([^']*)'", r'"\1"', carlist_str)
        # Remove trailing commas
        carlist_str = re.sub(r',\s*}', '}', carlist_str)
        carlist_str = re.sub(r',\s*]', ']', carlist_str)
        
        # Parse the JSON
        carlist_data = json.loads(carlist_str)
        
        logger.info(f"✅ Extracted carList with {len(carlist_data)} manufacturers")
        
        return carlist_data
        
    except Exception as e:
        logger.error(f"❌ Error extracting carList: {e}")
        return None

def build_carlist_mappings(raw_carlist):
    """Build the mapping structures needed by the service"""
    
    # Korean to English manufacturer mappings
    korean_to_english = {}
    english_to_korean = {}
    
    # Known manufacturer mappings
    manufacturer_mappings = {
        "현대": "HYUNDAI",
        "기아": "KIA", 
        "제네시스": "GENESIS",
        "쉐보레": "CHEVROLET",
        "쌍용": "SSANGYONG",
        "르노코리아": "RENAULT",
        "BMW": "BMW",
        "벤츠": "BENZ",
        "아우디": "AUDI",
        "폭스바겐": "VOLKSWAGEN",
        "미니": "MINI",
        "랜드로버": "LANDROVER",
        "재규어": "JAGUAR",
        "볼보": "VOLVO",
        "포르쉐": "PORSCHE",
        "지프": "JEEP",
        "포드": "FORD",
        "링컨": "LINCOLN",
        "캐딜락": "CADILLAC",
        "토요타": "TOYOTA",
        "렉서스": "LEXUS",
        "혼다": "HONDA",
        "닛산": "NISSAN",
        "인피니티": "INFINITI",
        "미쯔비시": "MITSUBISHI",
        "푸조": "PEUGEOT",
        "시트로엥": "CITROEN",
        "마세라티": "MASERATI",
        "벤틀리": "BENTLEY",
        "롤스로이스": "ROLLSROYCE",
        "테슬라": "TESLA",
        "람보르기니": "LAMBORGHINI",
        "페라리": "FERRARI",
    }
    
    # Build manufacturer mappings
    for korean_name in raw_carlist.keys():
        english_name = manufacturer_mappings.get(korean_name, korean_name.upper())
        korean_to_english[korean_name] = english_name
        english_to_korean[english_name] = korean_name
    
    # Build model mappings
    english_model_to_code = {}
    korean_model_to_code = {}
    
    for manufacturer_kr, models in raw_carlist.items():
        manufacturer_en = korean_to_english.get(manufacturer_kr, manufacturer_kr)
        
        if manufacturer_en not in english_model_to_code:
            english_model_to_code[manufacturer_en] = {}
        if manufacturer_kr not in korean_model_to_code:
            korean_model_to_code[manufacturer_kr] = {}
            
        for model in models:
            model_no = model.get("no", "")
            model_name_kr = model.get("name", "")
            model_name_en = model.get("e_name", model_name_kr)
            
            if model_name_en and model_no:
                english_model_to_code[manufacturer_en][model_name_en] = model_no
            if model_name_kr and model_no:
                korean_model_to_code[manufacturer_kr][model_name_kr] = model_no
    
    return {
        "korean_to_english_manufacturers": korean_to_english,
        "english_to_korean_manufacturers": english_to_korean,
        "english_model_to_code": english_model_to_code,
        "korean_model_to_code": korean_model_to_code,
        "full_carlist": raw_carlist
    }

def main():
    """Main function"""
    logger.info("🚀 Starting SSANCAR carList extraction...")
    
    # Extract carList from website
    raw_carlist = extract_carlist_from_ssancar()
    
    if not raw_carlist:
        logger.error("❌ Failed to extract carList")
        
        # Use sample data for testing
        logger.info("📋 Using sample carList data...")
        raw_carlist = {
            "현대": [
                {"no": "1", "name": "아반떼", "e_name": "AVANTE"},
                {"no": "2", "name": "쏘나타", "e_name": "SONATA"},
                {"no": "3", "name": "그랜저", "e_name": "GRANDEUR"},
                {"no": "4", "name": "투싼", "e_name": "TUCSON"},
                {"no": "5", "name": "싼타페", "e_name": "SANTA FE"},
                {"no": "6", "name": "팰리세이드", "e_name": "PALISADE"},
                {"no": "7", "name": "코나", "e_name": "KONA"},
                {"no": "8", "name": "아이오닉5", "e_name": "IONIQ 5"},
                {"no": "9", "name": "아이오닉6", "e_name": "IONIQ 6"},
                {"no": "10", "name": "넥쏘", "e_name": "NEXO"},
                {"no": "11", "name": "스타리아", "e_name": "STARIA"},
                {"no": "12", "name": "포터2", "e_name": "PORTER II"}
            ],
            "기아": [
                {"no": "21", "name": "K3", "e_name": "K3"},
                {"no": "22", "name": "K5", "e_name": "K5"},
                {"no": "23", "name": "K8", "e_name": "K8"}, 
                {"no": "24", "name": "K9", "e_name": "K9"},
                {"no": "25", "name": "셀토스", "e_name": "SELTOS"},
                {"no": "26", "name": "스포티지", "e_name": "SPORTAGE"},
                {"no": "27", "name": "쏘렌토", "e_name": "SORENTO"},
                {"no": "28", "name": "카니발", "e_name": "CARNIVAL"},
                {"no": "29", "name": "EV6", "e_name": "EV6"},
                {"no": "30", "name": "니로", "e_name": "NIRO"},
                {"no": "31", "name": "모닝", "e_name": "MORNING"},
                {"no": "32", "name": "레이", "e_name": "RAY"}
            ],
            "제네시스": [
                {"no": "41", "name": "G70", "e_name": "G70"},
                {"no": "42", "name": "G80", "e_name": "G80"},
                {"no": "43", "name": "G90", "e_name": "G90"},
                {"no": "44", "name": "GV60", "e_name": "GV60"},
                {"no": "45", "name": "GV70", "e_name": "GV70"},
                {"no": "46", "name": "GV80", "e_name": "GV80"},
                {"no": "47", "name": "GV90", "e_name": "GV90"}
            ],
            "쉐보레": [
                {"no": "51", "name": "스파크", "e_name": "SPARK"},
                {"no": "52", "name": "말리부", "e_name": "MALIBU"},
                {"no": "53", "name": "트레일블레이저", "e_name": "TRAILBLAZER"},
                {"no": "54", "name": "트래버스", "e_name": "TRAVERSE"},
                {"no": "55", "name": "콜로라도", "e_name": "COLORADO"},
                {"no": "56", "name": "타호", "e_name": "TAHOE"}
            ],
            "쌍용": [
                {"no": "61", "name": "티볼리", "e_name": "TIVOLI"},
                {"no": "62", "name": "코란도", "e_name": "KORANDO"},
                {"no": "63", "name": "렉스턴", "e_name": "REXTON"},
                {"no": "64", "name": "렉스턴 스포츠", "e_name": "REXTON SPORTS"},
                {"no": "65", "name": "토레스", "e_name": "TORRES"}
            ],
            "BMW": [
                {"no": "71", "name": "1시리즈", "e_name": "1 SERIES"},
                {"no": "72", "name": "2시리즈", "e_name": "2 SERIES"},
                {"no": "73", "name": "3시리즈", "e_name": "3 SERIES"},
                {"no": "74", "name": "4시리즈", "e_name": "4 SERIES"},
                {"no": "75", "name": "5시리즈", "e_name": "5 SERIES"},
                {"no": "76", "name": "7시리즈", "e_name": "7 SERIES"},
                {"no": "77", "name": "X1", "e_name": "X1"},
                {"no": "78", "name": "X3", "e_name": "X3"},
                {"no": "79", "name": "X5", "e_name": "X5"},
                {"no": "80", "name": "X7", "e_name": "X7"}
            ],
            "벤츠": [
                {"no": "91", "name": "A클래스", "e_name": "A-CLASS"},
                {"no": "92", "name": "C클래스", "e_name": "C-CLASS"},
                {"no": "93", "name": "E클래스", "e_name": "E-CLASS"},
                {"no": "94", "name": "S클래스", "e_name": "S-CLASS"},
                {"no": "95", "name": "GLA", "e_name": "GLA"},
                {"no": "96", "name": "GLC", "e_name": "GLC"},
                {"no": "97", "name": "GLE", "e_name": "GLE"},
                {"no": "98", "name": "GLS", "e_name": "GLS"}
            ],
            "아우디": [
                {"no": "101", "name": "A3", "e_name": "A3"},
                {"no": "102", "name": "A4", "e_name": "A4"},
                {"no": "103", "name": "A6", "e_name": "A6"},
                {"no": "104", "name": "A8", "e_name": "A8"},
                {"no": "105", "name": "Q3", "e_name": "Q3"},
                {"no": "106", "name": "Q5", "e_name": "Q5"},
                {"no": "107", "name": "Q7", "e_name": "Q7"},
                {"no": "108", "name": "Q8", "e_name": "Q8"}
            ]
        }
    
    # Build mapping structures
    carlist_data = build_carlist_mappings(raw_carlist)
    
    # Save to JSON file
    output_file = "ssancar_carlist.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(carlist_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ Successfully saved carList data to {output_file}")
    logger.info(f"📊 Total manufacturers: {len(carlist_data['korean_to_english_manufacturers'])}")
    
    # Print summary
    for manufacturer_kr, manufacturer_en in carlist_data['korean_to_english_manufacturers'].items():
        model_count = len(raw_carlist.get(manufacturer_kr, []))
        logger.info(f"  - {manufacturer_en} ({manufacturer_kr}): {model_count} models")

if __name__ == "__main__":
    main()