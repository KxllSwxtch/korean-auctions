#!/usr/bin/env python3
"""
Helper script to update PLC Auction cookies from browser

Instructions:
1. Open https://plc.auction in your browser
2. Open Developer Tools (F12)
3. Go to Network tab
4. Refresh the page
5. Click on any request to plc.auction
6. In the Headers tab, find the "Cookie" header
7. Copy the entire cookie string
8. Run this script and paste the cookie string when prompted
"""

import re
import json
from pathlib import Path
from datetime import datetime

def parse_cookie_string(cookie_string):
    """Parse a cookie string from browser into a dictionary"""
    cookies = {}
    
    # Split by semicolon and process each cookie
    for cookie in cookie_string.split(';'):
        cookie = cookie.strip()
        if '=' in cookie:
            name, value = cookie.split('=', 1)
            cookies[name.strip()] = value.strip()
    
    return cookies

def update_plc_cookies():
    """Update PLC Auction cookies"""
    print("=" * 60)
    print("PLC Auction Cookie Updater")
    print("=" * 60)
    print("\nFollow the instructions at the top of this script to get cookies from your browser.")
    print("\nPaste the entire cookie string from the browser (it should be one long line):")
    print("Example: intercom-id-m1d5ih1o=xxx; cf_clearance=yyy; XSRF-TOKEN=zzz; ...")
    print()
    
    cookie_string = input("Cookie string: ").strip()
    
    if not cookie_string:
        print("❌ No cookie string provided")
        return
    
    # Parse cookies
    cookies = parse_cookie_string(cookie_string)
    
    # Check for essential cookies
    essential_cookies = ['cf_clearance', 'XSRF-TOKEN', '__session']
    missing_cookies = [c for c in essential_cookies if c not in cookies]
    
    if missing_cookies:
        print(f"\n⚠️  Warning: Missing essential cookies: {', '.join(missing_cookies)}")
        proceed = input("Continue anyway? (y/n): ").lower()
        if proceed != 'y':
            return
    
    print(f"\n✅ Parsed {len(cookies)} cookies")
    
    # Update cars.py file
    cars_py_path = Path(__file__).parent.parent / "Glovis" / "cars.py"
    
    # Generate the new cars.py content
    new_content = f'''import requests

# Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (these cookies need to be refreshed when they expire)
cookies = {{
'''
    
    for name, value in cookies.items():
        new_content += f'    "{name}": "{value}",\n'
    
    new_content = new_content.rstrip(',\n') + '\n'
    new_content += '''}

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
    
    # Write the updated file
    with open(cars_py_path, 'w') as f:
        f.write(new_content)
    
    print(f"\n✅ Updated {cars_py_path}")
    
    # Also update the DEFAULT_COOKIES in plc_auction_service.py
    service_py_path = Path(__file__).parent.parent / "app" / "services" / "plc_auction_service.py"
    
    if service_py_path.exists():
        with open(service_py_path, 'r') as f:
            content = f.read()
        
        # Find and replace DEFAULT_COOKIES
        import re
        pattern = r'DEFAULT_COOKIES = \{[^}]+\}'
        
        new_default_cookies = 'DEFAULT_COOKIES = {\n'
        for name, value in cookies.items():
            new_default_cookies += f'        "{name}": "{value}",\n'
        new_default_cookies = new_default_cookies.rstrip(',\n') + '\n    }'
        
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, new_default_cookies, content, flags=re.DOTALL)
            with open(service_py_path, 'w') as f:
                f.write(content)
            print(f"✅ Updated DEFAULT_COOKIES in {service_py_path}")
    
    # Clear the session cache
    session_file = Path(__file__).parent.parent / "cache" / "sessions" / "plc_auction_session.json"
    if session_file.exists():
        session_file.unlink()
        print(f"✅ Cleared session cache")
    
    print("\n🎉 Cookie update complete!")
    print("\nYou can now test the PLC Auction service. The 403 error should be resolved.")

if __name__ == "__main__":
    update_plc_cookies()