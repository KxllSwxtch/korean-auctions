#!/usr/bin/env python3
"""
Easy cookie capture helper for PLC Auction
Simplifies the process of getting cookies from your browser
"""

import json
import os
from datetime import datetime
# Optional clipboard support
try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False

def parse_cookie_string(cookie_string):
    """Parse a cookie string from browser into a dictionary"""
    cookies = {}
    
    # Handle both semicolon and newline separated cookies
    cookie_string = cookie_string.replace('\n', '; ')
    
    for cookie in cookie_string.split('; '):
        cookie = cookie.strip()
        if '=' in cookie and cookie:
            key, value = cookie.split('=', 1)
            cookies[key.strip()] = value.strip()
    
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
    print("🍪 Easy PLC Auction Cookie Capture")
    print("==================================\n")
    
    print("Instructions:")
    print("1. Open Chrome/Edge and go to: https://plc.auction/ru/auction")
    print("2. Open Developer Tools (F12)")
    print("3. Go to Application/Storage tab → Cookies → https://plc.auction")
    print("4. You should see cookies like: cf_clearance, XSRF-TOKEN, __session, etc.\n")
    
    print("Now choose how to input cookies:\n")
    print("1. Copy all cookies as text (easiest)")
    print("2. Input cookies one by one")
    if HAS_CLIPBOARD:
        print("3. Paste from clipboard")
    print("4. Use browser console method\n")
    
    choice = input("Enter your choice (1-4): ").strip()
    
    cookies = {}
    
    if choice == "1":
        print("\nCopy all cookies from DevTools (you can select all and copy)")
        print("Paste them below (press Enter twice when done):\n")
        
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        
        cookie_text = '\n'.join(lines)
        cookies = parse_cookie_string(cookie_text)
        
    elif choice == "2":
        print("\nEnter cookies one by one (or 'done' when finished):")
        print("Format: cookie_name=cookie_value\n")
        
        while True:
            cookie_input = input("Cookie (or 'done'): ").strip()
            if cookie_input.lower() == 'done':
                break
            if '=' in cookie_input:
                key, value = cookie_input.split('=', 1)
                cookies[key.strip()] = value.strip()
                print(f"✓ Added {key}")
    
    elif choice == "3":
        if HAS_CLIPBOARD:
            try:
                print("\nTrying to read from clipboard...")
                clipboard_content = pyperclip.paste()
                cookies = parse_cookie_string(clipboard_content)
                print(f"✓ Found {len(cookies)} cookies from clipboard")
            except Exception as e:
                print(f"❌ Could not read from clipboard: {e}")
                return
        else:
            print("❌ Clipboard support not available. Install pyperclip: pip install pyperclip")
            return
    
    elif choice == "4":
        print("\nBrowser Console Method:")
        print("1. Open browser console on PLC Auction page")
        print("2. Run this JavaScript:")
        print("\n   document.cookie.split('; ').forEach(c => console.log(c))\n")
        print("3. Copy the output and paste below (press Enter twice):\n")
        
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        
        cookie_text = '\n'.join(lines)
        cookies = parse_cookie_string(cookie_text)
    
    if cookies:
        print(f"\n✅ Captured {len(cookies)} cookies:")
        for key in cookies:
            print(f"   - {key}")
        
        # Check for essential cookies
        essential = ['cf_clearance', 'XSRF-TOKEN', '__session']
        missing = [c for c in essential if c not in cookies]
        
        if missing:
            print(f"\n⚠️  Missing essential cookies: {', '.join(missing)}")
            proceed = input("\nProceed anyway? (y/n): ")
            if proceed.lower() != 'y':
                return
        
        # Update all files
        update_all_files(cookies)
        
        print("\n🎉 All files updated successfully!")
        print("\nNext steps:")
        print("1. Run: source venv/bin/activate")
        print("2. Run: python test_plc_rum.py")
    else:
        print("\n❌ No cookies captured")

if __name__ == "__main__":
    main()