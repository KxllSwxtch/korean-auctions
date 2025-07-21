#!/usr/bin/env python3
"""
Clean up the ssancar_carlist.json file to remove Unicode escapes
"""
import json

def cleanup_json():
    """Load JSON and save it back without Unicode escapes"""
    
    # Load the JSON file
    with open('ssancar_carlist.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # The JSON module automatically handles Unicode escapes when loading
    # Just save it back with ensure_ascii=False
    with open('ssancar_carlist.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("✅ Cleaned up ssancar_carlist.json - Unicode escapes removed")
    
    # Print some stats
    full_carlist = data.get('full_carlist', {})
    print(f"\nStats:")
    print(f"- Manufacturers: {len(full_carlist)}")
    print(f"- First 5 manufacturers: {list(full_carlist.keys())[:5]}")
    
    # Count total models
    total_models = sum(len(models) for models in full_carlist.values())
    print(f"- Total models: {total_models}")

if __name__ == "__main__":
    cleanup_json()