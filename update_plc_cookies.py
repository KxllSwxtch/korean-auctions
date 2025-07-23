#!/usr/bin/env python3
"""
Helper script to update PLC Auction cookies
Instructions:
1. Open https://plc.auction/auction in Chrome
2. Open Developer Tools (F12)
3. Go to Network tab
4. Reload the page
5. Find the 'auction' request
6. Right-click → Copy → Copy as cURL (bash)
7. Paste the cURL command below and run this script
"""

import re
import json
import os
from datetime import datetime

def extract_cookies_from_curl(curl_command):
    """Extract cookies from a cURL command"""
    cookies = {}
    
    # Find all cookie header values
    cookie_pattern = r"-H\s+['\"]cookie:\s*([^'\"]+)['\"]"
    cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
    
    if cookie_match:
        cookie_string = cookie_match.group(1)
        # Parse individual cookies
        for cookie in cookie_string.split('; '):
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                cookies[name.strip()] = value.strip()
    
    return cookies

def update_cookies_file(cookies):
    """Update the Glovis/cars.py file with new cookies"""
    template = '''import requests

cookies = {
'''
    
    for name, value in cookies.items():
        template += f'    "{name}": "{value}",\n'
    
    template += '''}

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "referer": "https://plc.auction/",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

params = {
    "page": "2",
    "country": "kr",
    "date": "1753131600",
    "price_type": "auction",
}

response = requests.get(
    "https://plc.auction/auction", params=params, cookies=cookies, headers=headers
)
'''
    
    # Write to file
    output_path = os.path.join(os.path.dirname(__file__), "Glovis", "cars.py")
    with open(output_path, 'w') as f:
        f.write(template)
    
    print(f"✅ Updated {output_path}")

def update_service_defaults(cookies):
    """Generate code to update DEFAULT_COOKIES in plc_auction_service.py"""
    print("\n📋 Copy this to update DEFAULT_COOKIES in plc_auction_service.py:")
    print("    DEFAULT_COOKIES = {")
    
    essential_cookies = [
        'intercom-id-m1d5ih1o',
        'intercom-device-id-m1d5ih1o',
        '_plc_ref',
        '_locale',
        'intercom-session-m1d5ih1o',
        'cf_clearance',
        'XSRF-TOKEN',
        '__session'
    ]
    
    for name in essential_cookies:
        if name in cookies:
            print(f'        "{name}": "{cookies[name]}",')
        else:
            print(f'        "{name}": "",  # Not found in curl')
    
    print("    }")

def main():
    print("🍪 PLC Auction Cookie Updater")
    print("=" * 50)
    
    # Option 1: Paste cURL command
    print("\nOption 1: Paste your cURL command (press Enter twice when done):")
    lines = []
    while True:
        line = input()
        if not line:
            break
        lines.append(line)
    
    curl_command = ' '.join(lines)
    
    if curl_command.strip():
        cookies = extract_cookies_from_curl(curl_command)
        
        if cookies:
            print(f"\n✅ Found {len(cookies)} cookies")
            
            # Show essential cookies
            essential = ['cf_clearance', 'XSRF-TOKEN', '__session']
            print("\n🔑 Essential cookies:")
            for name in essential:
                if name in cookies:
                    value = cookies[name]
                    print(f"  {name}: {value[:20]}...")
                else:
                    print(f"  {name}: ❌ NOT FOUND")
            
            # Update files
            update_cookies_file(cookies)
            update_service_defaults(cookies)
            
            # Save to JSON for backup
            backup_path = f"plc_cookies_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_path, 'w') as f:
                json.dump(cookies, f, indent=2)
            print(f"\n💾 Backup saved to {backup_path}")
            
        else:
            print("\n❌ No cookies found in cURL command")
    else:
        # Option 2: Manual entry
        print("\nOption 2: Enter cookies manually")
        cookies = {}
        
        essential = ['cf_clearance', 'XSRF-TOKEN', '__session']
        for name in essential:
            value = input(f"Enter {name}: ").strip()
            if value:
                cookies[name] = value
        
        if cookies:
            update_service_defaults(cookies)

if __name__ == "__main__":
    main()