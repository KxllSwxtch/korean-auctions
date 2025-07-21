#!/usr/bin/env python3
"""
Properly fix the ssancar_carlist.json file
"""
import json
import codecs

def decode_unicode_escapes(obj):
    """Recursively decode Unicode escapes in a dictionary or list"""
    if isinstance(obj, dict):
        return {
            (codecs.decode(k, 'unicode-escape') if isinstance(k, str) and '\\u' in k else k): 
            decode_unicode_escapes(v) for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [decode_unicode_escapes(item) for item in obj]
    elif isinstance(obj, str) and '\\u' in obj:
        return codecs.decode(obj, 'unicode-escape')
    else:
        return obj

def fix_json():
    """Fix the JSON file by properly decoding all Unicode escapes"""
    
    # Load the JSON file
    with open('ssancar_carlist.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Decode Unicode escapes in the entire structure
    fixed_data = decode_unicode_escapes(data)
    
    # Save it back
    with open('ssancar_carlist.json', 'w', encoding='utf-8') as f:
        json.dump(fixed_data, f, ensure_ascii=False, indent=2)
    
    print("✅ Fixed ssancar_carlist.json - All Unicode escapes decoded")
    
    # Print some stats
    full_carlist = fixed_data.get('full_carlist', {})
    print(f"\nStats:")
    print(f"- Manufacturers: {len(full_carlist)}")
    print(f"- First 5 manufacturers: {list(full_carlist.keys())[:5]}")
    
    # Show some examples
    for manufacturer in list(full_carlist.keys())[:3]:
        models = full_carlist[manufacturer]
        if models:
            print(f"\n{manufacturer}:")
            for model in models[:3]:
                print(f"  - {model['name']} ({model['e_name']})")

if __name__ == "__main__":
    fix_json()