#!/usr/bin/env python3
"""
Script to fetch all bike models from Bikemart API and generate translations
for Korean model names to English and Russian.
"""

import json
import re
import time
from typing import Dict, List, Set, Tuple
import requests
from pathlib import Path
import shutil
from datetime import datetime

# API configuration
BASE_URL = "https://shop.bikemart.co.kr/api/index.php"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "content-type": "application/x-www-form-urlencoded;charset=utf-8;",
    "origin": "https://bikeweb.bikemart.co.kr",
    "priority": "u=1, i",
    "referer": "https://bikeweb.bikemart.co.kr/",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

# Translation paths
FRONTEND_PATH = Path(__file__).parent.parent / "autobaza"
EN_TRANSLATION_PATH = FRONTEND_PATH / "lib/i18n/translations/en.json"
RU_TRANSLATION_PATH = FRONTEND_PATH / "lib/i18n/translations/ru.json"

# Korean pattern
KOREAN_PATTERN = re.compile(r'[가-힣]+')

# Common Korean terms translations
KOREAN_TERMS = {
    # Years
    "년식": ("", ""),  # Will be handled specially
    "년형": ("model", "модель"),
    "년": ("", ""),  # Will be handled specially
    
    # Conditions
    "신차급": ("like new", "как новый"),
    "신차": ("new", "новый"),
    "중고": ("used", "б/у"),
    "무사고": ("accident-free", "без аварий"),
    
    # Transaction types
    "팝니다": ("for sale", "продается"),
    "판매중": ("on sale", "в продаже"),
    "판매": ("sale", "продажа"),
    "리스": ("lease", "лизинг"),
    "렌트": ("rent", "аренда"),
    "할부": ("installment", "рассрочка"),
    
    # Quantities
    "키로": ("km", "км"),
    "킬로": ("km", "км"),
    "천": ("thousand", "тысяч"),
    "만": ("10k", "10 тыс"),
    
    # Months
    "월": ("", ""),  # Will be handled specially
    "출고": ("delivered", "поставлен"),
    "출시": ("released", "выпущен"),
    
    # Vehicle types
    "스쿠터": ("scooter", "скутер"),
    "오토바이": ("motorcycle", "мотоцикл"),
    "바이크": ("bike", "байк"),
    "네이키드": ("naked", "нейкед"),
    "투어러": ("tourer", "турер"),
    "크루저": ("cruiser", "круизер"),
    "스포츠": ("sport", "спорт"),
    "어드벤처": ("adventure", "эдвенчер"),
    
    # Other common terms
    "대": ("units", "единиц"),
    "입니다": ("", ""),  # Is/am/are - usually omitted
    "있습니다": ("available", "доступно"),
    "없습니다": ("not available", "недоступно"),
    "급": ("urgent", "срочно"),
    "특별": ("special", "специальный"),
    "한정": ("limited", "ограниченный"),
    "에디션": ("edition", "издание"),
    "모델": ("model", "модель"),
    "시리즈": ("series", "серия"),
    "타입": ("type", "тип"),
    "버전": ("version", "версия"),
    "사양": ("spec", "спецификация"),
    "풀옵션": ("full option", "полная комплектация"),
    "기본": ("basic", "базовая"),
    "프리미엄": ("premium", "премиум"),
    "스페셜": ("special", "специальная"),
}

# Korean brand names to English/Russian
KOREAN_BRANDS = {
    # Japanese brands
    "혼다": ("Honda", "Хонда"),
    "야마하": ("Yamaha", "Ямаха"),
    "스즈키": ("Suzuki", "Сузуки"),
    "가와사키": ("Kawasaki", "Кавасаки"),
    "스즈끼": ("Suzuki", "Сузуки"),  # Alternative spelling
    
    # European brands
    "두카티": ("Ducati", "Дукати"),
    "비엠더블유": ("BMW", "БМВ"),
    "비엠더블유": ("BMW", "БМВ"),
    "아프릴리아": ("Aprilia", "Априлия"),
    "트라이엄프": ("Triumph", "Триумф"),
    "베스파": ("Vespa", "Веспа"),
    "피아지오": ("Piaggio", "Пьяджио"),
    "모토구찌": ("Moto Guzzi", "Мото Гуцци"),
    "허스크바나": ("Husqvarna", "Хускварна"),
    
    # American brands
    "할리데이비슨": ("Harley-Davidson", "Харлей-Дэвидсон"),
    "할리": ("Harley", "Харлей"),
    "인디언": ("Indian", "Индиан"),
    
    # Korean brands
    "대림": ("Daelim", "Дэлим"),
    "효성": ("Hyosung", "Хёсунг"),
    "에스앤티": ("S&T", "С&Т"),
    
    # Chinese/Taiwanese brands
    "심": ("SYM", "СИМ"),
    "킴코": ("Kymco", "Кимко"),
    "시파": ("CF Moto", "СФ Мото"),
    
    # Other brands
    "로얄엔필드": ("Royal Enfield", "Роял Энфилд"),
    "베넬리": ("Benelli", "Бенелли"),
    "짐스타": ("Gymstar", "Гимстар"),
}


def fetch_brands() -> List[Dict]:
    """Fetch all bike brands from the API."""
    params = {
        "program": "bike",
        "service": "sell",
        "version": "1.0",
        "action": "getBikeBrandList",
        "token": "",
    }
    
    try:
        response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ResultCode"):
            return data.get("data", [])
        else:
            print(f"Error fetching brands: {data.get('ResultMessage', 'Unknown error')}")
            return []
    except Exception as e:
        print(f"Exception fetching brands: {e}")
        return []


def fetch_models_for_brand(brand_seq: str) -> List[Dict]:
    """Fetch all models for a specific brand."""
    params = {
        "brand": brand_seq,
        "program": "bike",
        "service": "sell",
        "version": "1.0",
        "action": "getBikeModel",
        "token": "",
    }
    
    try:
        response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ResultCode"):
            return data.get("data", [])
        else:
            print(f"Error fetching models for brand {brand_seq}: {data.get('ResultMessage', 'Unknown error')}")
            return []
    except Exception as e:
        print(f"Exception fetching models for brand {brand_seq}: {e}")
        return []


def translate_korean_text(text: str) -> Tuple[str, str]:
    """
    Translate Korean text to English and Russian.
    Returns tuple of (english_translation, russian_translation)
    """
    en_translation = text
    ru_translation = text
    
    # First, replace brand names
    for korean_brand, (en_brand, ru_brand) in KOREAN_BRANDS.items():
        en_translation = en_translation.replace(korean_brand, en_brand)
        ru_translation = ru_translation.replace(korean_brand, ru_brand)
    
    # Handle year patterns (e.g., "2021년식" -> "2021")
    year_pattern = re.compile(r'(\d{2,4})년식')
    en_translation = year_pattern.sub(r'\1', en_translation)
    ru_translation = year_pattern.sub(r'\1', ru_translation)
    
    # Handle year only patterns (e.g., "2021년" -> "2021")
    year_only_pattern = re.compile(r'(\d{2,4})년')
    en_translation = year_only_pattern.sub(r'\1', en_translation)
    ru_translation = year_only_pattern.sub(r'\1', ru_translation)
    
    # Handle month patterns (e.g., "6월" -> "June" / "июнь")
    months_en = ["January", "February", "March", "April", "May", "June", 
                 "July", "August", "September", "October", "November", "December"]
    months_ru = ["январь", "февраль", "март", "апрель", "май", "июнь",
                 "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    
    month_pattern = re.compile(r'(\d{1,2})월')
    month_matches = month_pattern.findall(en_translation)
    for month_str in month_matches:
        month_num = int(month_str)
        if 1 <= month_num <= 12:
            en_translation = en_translation.replace(f"{month_str}월", months_en[month_num - 1])
            ru_translation = ru_translation.replace(f"{month_str}월", months_ru[month_num - 1])
    
    # Replace known Korean terms (after brands to avoid conflicts)
    for korean_term, (en_term, ru_term) in KOREAN_TERMS.items():
        if en_term:  # Only replace if translation exists
            en_translation = en_translation.replace(korean_term, en_term)
        if ru_term:
            ru_translation = ru_translation.replace(korean_term, ru_term)
    
    # Handle special patterns
    # Pattern: "숫자천" -> "숫자,000" (e.g., "15천" -> "15,000")
    thousand_pattern = re.compile(r'(\d+)천')
    en_translation = thousand_pattern.sub(lambda m: f"{int(m.group(1)):,}000", en_translation)
    ru_translation = thousand_pattern.sub(lambda m: f"{int(m.group(1)):,}000", ru_translation)
    
    # Pattern: "숫자만" -> "숫자0,000" (e.g., "3만" -> "30,000")
    tenk_pattern = re.compile(r'(\d+)만')
    en_translation = tenk_pattern.sub(lambda m: f"{int(m.group(1)):,}0000", en_translation)
    ru_translation = tenk_pattern.sub(lambda m: f"{int(m.group(1)):,}0000", ru_translation)
    
    # Clean up multiple spaces and normalize
    en_translation = ' '.join(en_translation.split())
    ru_translation = ' '.join(ru_translation.split())
    
    # Remove any remaining Korean text that couldn't be translated
    # Only if significant portion was translated
    en_words = en_translation.split()
    ru_words = ru_translation.split()
    en_korean_count = sum(1 for word in en_words if KOREAN_PATTERN.search(word))
    ru_korean_count = sum(1 for word in ru_words if KOREAN_PATTERN.search(word))
    
    # If more than 50% is still Korean, return original
    if len(en_words) > 0 and en_korean_count / len(en_words) > 0.5:
        en_translation = text
    if len(ru_words) > 0 and ru_korean_count / len(ru_words) > 0.5:
        ru_translation = text
    
    return en_translation.strip(), ru_translation.strip()


def load_existing_translations(file_path: Path) -> Dict:
    """Load existing translations from file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return {}


def save_translations(file_path: Path, translations: Dict):
    """Save translations to file."""
    # Create backup
    if file_path.exists():
        backup_path = file_path.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        shutil.copy2(file_path, backup_path)
        print(f"Created backup: {backup_path}")
    
    # Save translations
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)
    print(f"Saved translations to: {file_path}")


def main():
    """Main function to fetch all models and generate translations."""
    print("Starting bike models translation fetch...")
    
    # Fetch all brands
    print("\nFetching all brands...")
    brands = fetch_brands()
    print(f"Found {len(brands)} brands")
    
    # Collect all models with Korean text
    korean_models: Set[str] = set()
    total_models = 0
    
    print("\nFetching models for each brand...")
    # Process only brands with Korean names first (they likely have Korean models)
    brands_sorted = sorted(brands, key=lambda b: (
        0 if KOREAN_PATTERN.search(b.get("brand_name", "")) else 1,
        b.get("brand_name", "")
    ))
    
    # Limit to first 30 brands for initial run
    brands_to_process = brands_sorted[:30]
    print(f"Processing {len(brands_to_process)} brands (out of {len(brands)} total)")
    
    for i, brand in enumerate(brands_to_process):
        brand_seq = brand.get("seq", "")
        brand_name = brand.get("brand_name", "Unknown")
        
        if not brand_seq:
            continue
        
        print(f"[{i+1}/{len(brands_to_process)}] Fetching models for {brand_name} (seq: {brand_seq})...")
        
        # Rate limiting
        time.sleep(0.3)
        
        models = fetch_models_for_brand(brand_seq)
        total_models += len(models)
        
        # Find models with Korean text
        korean_count = 0
        for model in models:
            model_name = model.get("model", "")
            if model_name and KOREAN_PATTERN.search(model_name):
                korean_models.add(model_name)
                korean_count += 1
        
        if korean_count > 0:
            print(f"  Found {korean_count} models with Korean text")
    
    print(f"\nTotal models found: {total_models}")
    print(f"Models with Korean text: {len(korean_models)}")
    
    # Generate translations
    print("\nGenerating translations...")
    model_translations_en = {}
    model_translations_ru = {}
    
    for model_name in sorted(korean_models):
        en_translation, ru_translation = translate_korean_text(model_name)
        
        # Only add if translation is different from original
        if en_translation != model_name:
            model_translations_en[model_name] = en_translation
        if ru_translation != model_name:
            model_translations_ru[model_name] = ru_translation
    
    print(f"Generated {len(model_translations_en)} English translations")
    print(f"Generated {len(model_translations_ru)} Russian translations")
    
    # Load existing translations
    print("\nLoading existing translations...")
    en_translations = load_existing_translations(EN_TRANSLATION_PATH)
    ru_translations = load_existing_translations(RU_TRANSLATION_PATH)
    
    # Merge with existing translations
    if "bikes" not in en_translations:
        en_translations["bikes"] = {}
    if "models" not in en_translations["bikes"]:
        en_translations["bikes"]["models"] = {}
    
    if "bikes" not in ru_translations:
        ru_translations["bikes"] = {}
    if "models" not in ru_translations["bikes"]:
        ru_translations["bikes"]["models"] = {}
    
    # Update model translations while preserving existing ones
    en_translations["bikes"]["models"].update(model_translations_en)
    ru_translations["bikes"]["models"].update(model_translations_ru)
    
    # Save updated translations
    print("\nSaving updated translations...")
    save_translations(EN_TRANSLATION_PATH, en_translations)
    save_translations(RU_TRANSLATION_PATH, ru_translations)
    
    # Print summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Total brands processed: {len(brands_to_process)} (out of {len(brands)})")
    print(f"Total models found: {total_models}")
    print(f"Models with Korean text: {len(korean_models)}")
    print(f"English translations added: {len(model_translations_en)}")
    print(f"Russian translations added: {len(model_translations_ru)}")
    print("\nSample translations:")
    for i, (original, translation) in enumerate(list(model_translations_en.items())[:10]):
        print(f"  {original} -> EN: {translation} / RU: {model_translations_ru.get(original, 'N/A')}")
    
    print("\nTranslation update complete!")


if __name__ == "__main__":
    main()