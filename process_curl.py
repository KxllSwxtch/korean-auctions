#!/usr/bin/env python3
"""
Process a fresh cURL request and update PLC Auction cookies
"""

import re
import json
import os
from datetime import datetime

def extract_cookies_from_curl(curl_command):
    """Extract cookies from a cURL command"""
    # Find all cookie headers
    cookie_pattern = r"-H ['\"]cookie: ([^'\"]+)['\"]"
    cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
    
    if not cookie_match:
        print("No cookies found in cURL command")
        return None
    
    cookie_string = cookie_match.group(1)
    
    # Parse cookies
    cookies = {}
    for cookie in cookie_string.split('; '):
        if '=' in cookie:
            key, value = cookie.split('=', 1)
            cookies[key] = value
    
    # Extract XSRF token from headers
    xsrf_pattern = r"-H ['\"]x-xsrf-token: ([^'\"]+)['\"]"
    xsrf_match = re.search(xsrf_pattern, curl_command, re.IGNORECASE)
    
    if xsrf_match:
        cookies['XSRF-TOKEN'] = xsrf_match.group(1)
    
    return cookies

def update_all_files(cookies):
    """Update all necessary files with fresh cookies"""
    # Update cars.py
    code_lines = ['import requests\n\n', 'cookies = {\n']
    
    for key, value in cookies.items():
        code_lines.append(f'    "{key}": "{value}",\n')
    
    code_lines.append('}\n\n')
    
    # Add headers
    code_lines.extend([
        'headers = {\n',
        '    "accept": "application/json, text/plain, */*",\n',
        '    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",\n',
        '    "content-type": "application/json",\n',
        '    "origin": "https://plc.auction",\n',
        '    "priority": "u=1, i",\n',
        '    "referer": "https://plc.auction/ru/auction?country=kr&damage=none&date=1753304400",\n',
        '    "sec-ch-ua": \'"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"\',\n',
        '    "sec-ch-ua-mobile": "?0",\n',
        '    "sec-ch-ua-platform": \'"macOS"\',\n',
        '    "sec-fetch-dest": "empty",\n',
        '    "sec-fetch-mode": "cors",\n',
        '    "sec-fetch-site": "same-origin",\n',
        '    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",\n',
        '    "x-requested-with": "XMLHttpRequest",\n'
    ])
    
    if "XSRF-TOKEN" in cookies:
        code_lines.append(f'    "x-xsrf-token": "{cookies["XSRF-TOKEN"]}",\n')
    
    code_lines.extend([
        '}\n\n',
        'json_data = {\n',
        '    "country": "kr",\n',
        '    "date": "1753304400",\n',
        '}\n\n',
        'response = requests.post(\n',
        '    "https://plc.auction/ru/auction/request",\n',
        '    cookies=cookies,\n',
        '    headers=headers,\n',
        '    json=json_data,\n',
        ')\n'
    ])
    
    # Write to cars.py
    with open('Glovis/cars.py', 'w') as f:
        f.writelines(code_lines)
    
    print("✅ Updated Glovis/cars.py")
    
    # Update session cache
    cache_dir = "cache/sessions"
    os.makedirs(cache_dir, exist_ok=True)
    
    session_data = {
        "cookies": cookies,
        "timestamp": datetime.now().isoformat(),
        "metadata": {}
    }
    
    with open(f"{cache_dir}/plc_auction_session.json", 'w') as f:
        json.dump(session_data, f, indent=2)
    
    print(f"✅ Updated {cache_dir}/plc_auction_session.json")

def main():
    print("🍪 PLC Auction Cookie Processor")
    print("================================\n")
    
    print("Please paste your fresh cURL request below.")
    print("(Press Enter twice when done)\n")
    
    # Read multi-line input
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    
    curl_command = " ".join(lines)
    
    if curl_command:
        cookies = extract_cookies_from_curl(curl_command)
        if cookies:
            print(f"\n✅ Found {len(cookies)} cookies:")
            for key in cookies:
                print(f"   - {key}")
            
            # Update all files
            update_all_files(cookies)
            
            print("\n🎉 All files updated successfully!")
            print("\n📋 Next steps:")
            print("1. Run: source venv/bin/activate")
            print("2. Run: python test_plc_rum.py")
            print("\nThe API should now work with the fresh cookies!")
        else:
            print("\n❌ Failed to extract cookies from the cURL command")
    else:
        print("\n❌ No cURL command provided")

if __name__ == "__main__":
    main()