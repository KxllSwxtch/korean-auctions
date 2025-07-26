#!/usr/bin/env python3
"""
Script to fix and clean up bike model translations
"""

import json
from pathlib import Path

# Translation paths
FRONTEND_PATH = Path(__file__).parent.parent / "autobaza"
EN_TRANSLATION_PATH = FRONTEND_PATH / "lib/i18n/translations/en.json"
RU_TRANSLATION_PATH = FRONTEND_PATH / "lib/i18n/translations/ru.json"

# Load translations
with open(EN_TRANSLATION_PATH, 'r', encoding='utf-8') as f:
    en_data = json.load(f)

with open(RU_TRANSLATION_PATH, 'r', encoding='utf-8') as f:
    ru_data = json.load(f)

# Get model translations
en_models = en_data.get("bikes", {}).get("models", {})
ru_models = ru_data.get("bikes", {}).get("models", {})

# Clean up problematic translations
fixes_en = {}
fixes_ru = {}

for key, value in en_models.items():
    # Skip if already good
    if key == value:
        continue
    
    # Fix specific issues
    fixed_en = value
    fixed_ru = ru_models.get(key, key)
    
    # Fix duplicate brand names
    fixed_en = fixed_en.replace("SYM 크루SYM", "SYM Crusym")
    fixed_ru = fixed_ru.replace("SYM 크루СИМ", "SYM Крусим")
    
    # Fix untranslated Korean words
    if "두카티" in fixed_en:
        fixed_en = fixed_en.replace("두카티", "Ducati")
    if "Дукати" not in fixed_ru and "두카티" in fixed_ru:
        fixed_ru = fixed_ru.replace("두카티", "Дукати")
        
    # Fix year patterns
    fixed_en = fixed_en.replace("주year", " Year Anniversary")
    fixed_ru = fixed_ru.replace("주year", "-летие")
    
    # Fix model word
    fixed_en = fixed_en.replace("model", " model")
    fixed_ru = fixed_ru.replace("модель", " модель")
    
    # Fix lease word
    fixed_en = fixed_en.replace("lease", "lease")
    fixed_ru = fixed_ru.replace("лизинг", "лизинг")
    
    # Fix remaining Korean terms
    korean_fixes = {
        "모터": "Motor",
        "스페셜": "Special",
        "에디션": "Edition", 
        "리미티드": "Limited",
        "애니버서리": "Anniversary",
        "어드벤쳐": "Adventure",
        "스포츠": "Sport",
        "투어링": "Touring",
        "프리미엄": "Premium",
        "슈퍼": "Super",
        "블랙": "Black",
        "화이트": "White",
        "골드": "Gold",
        "레전드": "Legend",
        "히어로": "Hero",
        "트리플": "Triple",
        "알파인": "Alpine",
        "록스타": "Rockstar",
        "테크": "Tech",
        "프로": "Pro",
        "플러스": "Plus",
        "스크램블러": "Scrambler",
        "커스텀": "Custom",
        "클래식": "Classic",
        "바이크": "Bike",
        "스쿠터": "Scooter",
        "오토바이": "Motorcycle"
    }
    
    korean_fixes_ru = {
        "모터": "Мотор",
        "스페셜": "Специальная",
        "에디션": "Издание",
        "리미티드": "Лимитированная",
        "애니버서리": "Юбилейная",
        "어드벤쳐": "Эдвенчер",
        "스포츠": "Спорт",
        "투어링": "Туринг",
        "프리미엄": "Премиум",
        "슈퍼": "Супер",
        "블랙": "Черный",
        "화이트": "Белый", 
        "골드": "Золотой",
        "레전드": "Легенда",
        "히어로": "Герой",
        "트리플": "Тройной",
        "알파인": "Альпийский",
        "록스타": "Рокстар",
        "테크": "Тех",
        "프로": "Про",
        "플러스": "Плюс",
        "스크램블러": "Скрамблер",
        "커스텀": "Кастом",
        "클래식": "Классик",
        "바이크": "Байк",
        "스쿠터": "Скутер",
        "오토바이": "Мотоцикл"
    }
    
    for kr_term, en_term in korean_fixes.items():
        if kr_term in fixed_en:
            fixed_en = fixed_en.replace(kr_term, en_term)
    
    for kr_term, ru_term in korean_fixes_ru.items():
        if kr_term in fixed_ru:
            fixed_ru = fixed_ru.replace(kr_term, ru_term)
    
    # Clean up spaces
    fixed_en = ' '.join(fixed_en.split())
    fixed_ru = ' '.join(fixed_ru.split())
    
    # Only update if changed
    if fixed_en != value:
        fixes_en[key] = fixed_en
    if fixed_ru != ru_models.get(key, key):
        fixes_ru[key] = fixed_ru

# Apply fixes
for key, value in fixes_en.items():
    en_data["bikes"]["models"][key] = value

for key, value in fixes_ru.items():
    ru_data["bikes"]["models"][key] = value

# Save files
with open(EN_TRANSLATION_PATH, 'w', encoding='utf-8') as f:
    json.dump(en_data, f, ensure_ascii=False, indent=2)

with open(RU_TRANSLATION_PATH, 'w', encoding='utf-8') as f:
    json.dump(ru_data, f, ensure_ascii=False, indent=2)

print(f"Fixed {len(fixes_en)} English translations")
print(f"Fixed {len(fixes_ru)} Russian translations")

# Show some examples
print("\nSample fixes:")
for i, (key, value) in enumerate(list(fixes_en.items())[:10]):
    original_en = en_models.get(key)
    original_ru = ru_models.get(key, key)
    new_ru = fixes_ru.get(key, original_ru)
    print(f"\n{key}:")
    print(f"  EN: {original_en} -> {value}")
    print(f"  RU: {original_ru} -> {new_ru}")