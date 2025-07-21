#!/usr/bin/env python3
"""
Script to extract carList data from SSANCAR HTML page
"""
import json
import re
import os

def extract_carlist_from_html():
    """Extract carList from the full-page.html file"""
    
    # Read the HTML file
    html_file = "Glovis/full-page.html"
    if not os.path.exists(html_file):
        print(f"Error: {html_file} not found!")
        return None
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Extract the carList JavaScript object using regex
    # The carList is defined between lines 632-1146 in the HTML
    pattern = r'const carList = ({[\s\S]*?})\s*\n\s*\$\(document\)'
    match = re.search(pattern, html_content)
    
    if not match:
        print("Error: Could not find carList in HTML!")
        return None
    
    carlist_js = match.group(1)
    
    # Convert JavaScript object to Python dict
    # Replace JavaScript syntax with Python syntax
    carlist_js = carlist_js.replace('no:', '"no":')
    carlist_js = carlist_js.replace('name:', '"name":')
    carlist_js = carlist_js.replace('e_name:', '"e_name":')
    
    # Parse the JSON
    try:
        carlist_data = json.loads(carlist_js)
    except json.JSONDecodeError as e:
        print(f"Error parsing carList: {e}")
        # Try manual parsing
        carlist_data = parse_carlist_manually(carlist_js)
    
    return carlist_data

def parse_carlist_manually(js_text):
    """Manually parse the JavaScript carList object"""
    carlist = {}
    
    # Find all manufacturer blocks
    manufacturers = re.findall(r'"([^"]+)":\s*\[([\s\S]*?)\](?=,\s*"|\s*})', js_text)
    
    for manufacturer, models_str in manufacturers:
        models = []
        # Find all model objects
        model_matches = re.findall(r'{[^}]+}', models_str)
        
        for model_match in model_matches:
            # Extract fields
            no_match = re.search(r'"no":\s*"([^"]+)"', model_match)
            name_match = re.search(r'"name":\s*"([^"]+)"', model_match)
            e_name_match = re.search(r'"e_name":\s*"([^"]+)"', model_match)
            
            if no_match and name_match and e_name_match:
                models.append({
                    "no": no_match.group(1),
                    "name": name_match.group(1),
                    "e_name": e_name_match.group(1)
                })
        
        carlist[manufacturer] = models
    
    return carlist

def update_ssancar_carlist():
    """Update the ssancar_carlist.json file with extracted data"""
    
    # Extract carList from HTML
    print("Extracting carList from HTML...")
    carlist_data = extract_carlist_from_html()
    
    if not carlist_data:
        print("Failed to extract carList data!")
        return
    
    # Load existing JSON file
    json_file = "ssancar_carlist.json"
    with open(json_file, 'r', encoding='utf-8') as f:
        existing_data = json.load(f)
    
    # Update full_carlist
    existing_data["full_carlist"] = carlist_data
    
    # Build english_model_to_code mapping
    english_model_to_code = {}
    korean_model_to_code = {}
    
    # Also update manufacturer mappings from carlist
    korean_to_english = existing_data.get("korean_to_english_manufacturers", {})
    english_to_korean = existing_data.get("english_to_korean_manufacturers", {})
    
    # Map from the extracted HTML (these are the actual mappings from SSANCAR)
    manufacturer_mapping = {
        "현대": "HYUNDAI",
        "기아": "KIA", 
        "한국지엠": "CHEVROLET",
        "르노삼성": "RENAULTSM",
        "쌍용": "KG",
        "제네시스": "GENESIS",
        "벤츠": "BENZ",
        "BMW": "BMW",
        "아우디": "AUDI",
        "폭스바겐": "VOLKSWAGEN",
        "랜드로버": "LANDRover",
        "미니": "Mini",
        "포드": "FORD",
        "닛산": "NISSAN",
        "토요타": "Toyota",
        "렉서스": "LEXUS",
        "마세라티": "MASERATI",
        "링컨": "LINCOLN",
        "벤틀리": "BENTLEY",
        "볼보": "VOLVO",
        "시트로엥": "CITROEN",
        "인피니티": "INFINITI",
        "재규어": "JAGUAR",
        "지프": "JEEP",
        "캐딜락": "CADILLAC",
        "크라이슬러": "CHRYSLER",
        "테슬라": "TESLA",
        "포르쉐": "PORSCHE",
        "푸조": "PEUGEOT",
        "피아트": "FIAT",
        "혼다": "HONDA"
    }
    
    # Update manufacturer mappings
    korean_to_english.update(manufacturer_mapping)
    for korean, english in manufacturer_mapping.items():
        english_to_korean[english] = korean
    
    existing_data["korean_to_english_manufacturers"] = korean_to_english
    existing_data["english_to_korean_manufacturers"] = english_to_korean
    
    for korean_manufacturer, models in carlist_data.items():
        english_manufacturer = korean_to_english.get(korean_manufacturer, korean_manufacturer)
        
        if english_manufacturer not in english_model_to_code:
            english_model_to_code[english_manufacturer] = {}
        if korean_manufacturer not in korean_model_to_code:
            korean_model_to_code[korean_manufacturer] = {}
        
        for model in models:
            # Map English name to code
            english_model_to_code[english_manufacturer][model["e_name"]] = model["no"]
            # Map Korean name to code
            korean_model_to_code[korean_manufacturer][model["name"]] = model["no"]
    
    existing_data["english_model_to_code"] = english_model_to_code
    existing_data["korean_model_to_code"] = korean_model_to_code
    
    # Save updated JSON
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
    
    print(f"Successfully updated {json_file}")
    print(f"Total manufacturers: {len(carlist_data)}")
    total_models = sum(len(models) for models in carlist_data.values())
    print(f"Total models: {total_models}")

if __name__ == "__main__":
    update_ssancar_carlist()