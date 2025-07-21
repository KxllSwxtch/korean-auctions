#!/usr/bin/env python3
"""
Fix the english_model_to_code mapping to use English manufacturer names as keys
"""
import json

def fix_model_mappings():
    """Fix the model mappings to use proper English manufacturer names"""
    
    # Load the JSON file
    with open('ssancar_carlist.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Get the Korean to English mapping
    korean_to_english = data['korean_to_english_manufacturers']
    
    # Fix english_model_to_code
    fixed_english_model_to_code = {}
    for korean_manufacturer, models in data['english_model_to_code'].items():
        english_manufacturer = korean_to_english.get(korean_manufacturer, korean_manufacturer)
        fixed_english_model_to_code[english_manufacturer] = models
    
    # Also handle BMW case in the full_carlist (BMW models are under 벤츠)
    # Let's separate BMW models from 벤츠
    if '벤츠' in data['full_carlist']:
        benz_models = []
        bmw_models = []
        
        for model in data['full_carlist']['벤츠']:
            # BMW series models
            if any(x in model['e_name'] for x in ['series', 'i3', 'i4', 'i7', 'i8', 'iX', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'M-series', 'Z4']):
                bmw_models.append(model)
            else:
                benz_models.append(model)
        
        # Update the full_carlist
        data['full_carlist']['벤츠'] = benz_models
        data['full_carlist']['BMW'] = bmw_models
        
        # Also update the model mappings
        if 'BENZ' in fixed_english_model_to_code:
            benz_model_map = {}
            bmw_model_map = {}
            
            for e_name, code in fixed_english_model_to_code['BENZ'].items():
                if any(x in e_name for x in ['series', 'i3', 'i4', 'i7', 'i8', 'iX', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'M-series', 'Z4']):
                    bmw_model_map[e_name] = code
                else:
                    benz_model_map[e_name] = code
            
            fixed_english_model_to_code['BENZ'] = benz_model_map
            fixed_english_model_to_code['BMW'] = bmw_model_map
    
    # Update the data
    data['english_model_to_code'] = fixed_english_model_to_code
    
    # Save back
    with open('ssancar_carlist.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("✅ Fixed model mappings")
    print(f"Manufacturers in english_model_to_code: {list(fixed_english_model_to_code.keys())[:10]}...")

if __name__ == "__main__":
    fix_model_mappings()