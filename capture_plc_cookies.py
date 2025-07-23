#!/usr/bin/env python3
"""
Script to help capture fresh cookies for PLC Auction API
Instructions:
1. Open Chrome DevTools (F12)
2. Go to https://plc.auction/auction?country=kr&date=1753304400&price_type=auction
3. Open Network tab
4. Find the "request" POST request to https://plc.auction/auction/request
5. Copy the cURL command (Right click -> Copy -> Copy as cURL)
6. Paste it into this script to extract cookies
"""

import re
import json
from datetime import datetime

def extract_cookies_from_curl(curl_command):
    """Extract cookies from a cURL command"""
    # Find all cookie headers
    cookie_pattern = r"-H 'cookie: ([^']+)'"
    cookie_match = re.search(cookie_pattern, curl_command, re.IGNORECASE)
    
    if not cookie_match:
        # Try double quotes
        cookie_pattern = r'-H "cookie: ([^"]+)"'
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

def generate_cookie_update(cookies):
    """Generate Python code to update cookies"""
    print("\n# Add these cookies to your PLCAuctionService DEFAULT_COOKIES:")
    print("DEFAULT_COOKIES = {")
    for key, value in cookies.items():
        print(f'    "{key}": "{value}",')
    print("}")
    
    print("\n# Or update via API:")
    print("curl -X POST 'http://localhost:8001/api/v1/glovis/update-cookies' \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -d '{")
    for i, (key, value) in enumerate(cookies.items()):
        comma = "," if i < len(cookies) - 1 else ""
        print(f'    "{key}": "{value}"{comma}')
    print("  }'")

def main():
    print("=== PLC Auction Cookie Capture Tool ===")
    print("\nInstructions:")
    print("1. Open Chrome DevTools (F12)")
    print("2. Go to https://plc.auction/auction?country=kr&date=1753304400&price_type=auction")
    print("3. Wait for the page to load completely")
    print("4. Open Network tab and clear it")
    print("5. Scroll down to trigger the AJAX request that loads cars")
    print("6. Find the 'request' POST request to https://plc.auction/auction/request")
    print("7. Right click on it -> Copy -> Copy as cURL")
    print("8. Paste the cURL command below (press Enter twice when done):\n")
    
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
            print(f"\n✅ Found {len(cookies)} cookies")
            
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"plc_cookies_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(cookies, f, indent=2)
            print(f"✅ Saved cookies to {filename}")
            
            generate_cookie_update(cookies)
        else:
            print("❌ Failed to extract cookies")
    else:
        print("❌ No cURL command provided")

if __name__ == "__main__":
    main()