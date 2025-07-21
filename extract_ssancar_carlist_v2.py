#!/usr/bin/env python3
"""
Script to extract carList data from SSANCAR HTML page - Version 2
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
    
    # Extract just the carList content
    # Find the part between "const carList = {" and the next "$(document).on"
    start_marker = "const carList = {"
    end_marker = "$(document).on"
    
    start_idx = html_content.find(start_marker)
    if start_idx == -1:
        print("Error: Could not find carList start marker!")
        return None
    
    # Find the closing brace before $(document).on
    content_after_start = html_content[start_idx + len(start_marker) - 1:]
    
    # Count braces to find the matching closing brace
    brace_count = 0
    end_idx = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(content_after_start):
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            continue
            
        if char == '"' and not in_string:
            in_string = True
        elif char == '"' and in_string:
            in_string = False
        elif not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
    
    if end_idx == 0:
        print("Error: Could not find matching closing brace!")
        return None
    
    carlist_js = content_after_start[:end_idx]
    
    # Now manually parse the JavaScript object
    carlist = {}
    
    # Find all manufacturer entries
    # Pattern to match: "manufacturer_name": [ ... array of models ... ]
    pattern = r'"([^"]+)":\s*\[([\s\S]*?)\](?=\s*,\s*"|}\s*$)'
    
    for match in re.finditer(pattern, carlist_js):
        manufacturer = match.group(1)
        models_str = match.group(2)
        
        models = []
        # Find all model objects within the array
        model_pattern = r'{\s*no:\s*"([^"]+)"\s*,\s*name:\s*"([^"]+)"\s*,\s*e_name:\s*"([^"]+)"\s*}'
        
        for model_match in re.finditer(model_pattern, models_str):
            models.append({
                "no": model_match.group(1),
                "name": model_match.group(2),
                "e_name": model_match.group(3)
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
    
    # Print extracted data for verification
    print(f"\nExtracted {len(carlist_data)} manufacturers:")
    for manufacturer, models in carlist_data.items():
        print(f"  {manufacturer}: {len(models)} models")
    
    # Create comprehensive mappings
    korean_to_english = {
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
    
    english_to_korean = {v: k for k, v in korean_to_english.items()}
    
    # Build model mappings
    english_model_to_code = {}
    korean_model_to_code = {}
    
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
    
    # Create the complete data structure
    complete_data = {
        "korean_to_english_manufacturers": korean_to_english,
        "english_to_korean_manufacturers": english_to_korean,
        "english_model_to_code": english_model_to_code,
        "korean_model_to_code": korean_model_to_code,
        "full_carlist": carlist_data
    }
    
    # Save to JSON file
    json_file = "ssancar_carlist.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(complete_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nSuccessfully updated {json_file}")
    total_models = sum(len(models) for models in carlist_data.values())
    print(f"Total models: {total_models}")

if __name__ == "__main__":
    update_ssancar_carlist()