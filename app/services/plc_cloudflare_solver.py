"""
Enhanced Cloudflare solver for PLC Auction using cloudscraper
"""

import cloudscraper
import json
import time
import random
from typing import Dict, Optional, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class PLCCloudflareSolver:
    """Enhanced Cloudflare solver with better browser emulation"""
    
    def __init__(self):
        self.session = None
        self.cookies = {}
        
    def create_enhanced_session(self) -> cloudscraper.CloudScraper:
        """Create a cloudscraper session with enhanced browser emulation"""
        
        # Browser configurations to try
        browser_configs = [
            {
                'browser': {
                    'browser': 'chrome',
                    'platform': 'darwin',
                    'desktop': True,
                    'mobile': False
                }
            },
            {
                'browser': {
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True,
                    'mobile': False
                }
            },
            {
                'browser': {
                    'browser': 'firefox',
                    'platform': 'darwin',
                    'desktop': True,
                    'mobile': False
                }
            }
        ]
        
        # Try different browser configurations
        for config in browser_configs:
            try:
                logger.info(f"🌐 Trying browser config: {config['browser']['browser']} on {config['browser']['platform']}")
                
                # Create scraper with specific browser config
                scraper = cloudscraper.create_scraper(
                    browser=config['browser'],
                    interpreter='nodejs',  # Use Node.js for better challenge solving
                    delay=10,  # Wait up to 10 seconds for challenge
                    debug=False
                )
                
                # Disable SSL verification for development (PLC has certificate issues)
                scraper.verify = False
                
                # Suppress SSL warnings
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                # Set realistic headers
                scraper.headers.update({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Ch-Ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"macOS"' if 'darwin' in config['browser']['platform'] else '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1'
                })
                
                return scraper
                
            except Exception as e:
                logger.warning(f"⚠️ Failed with config {config}: {e}")
                continue
        
        # Fallback to default
        logger.info("📱 Using default cloudscraper configuration")
        scraper = cloudscraper.create_scraper(interpreter='nodejs', delay=10)
        scraper.verify = False
        
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        return scraper
    
    def solve_challenge_and_get_cookies(self, url: str = "https://plc.auction/ru") -> Tuple[bool, Dict[str, str]]:
        """
        Visit the URL, solve Cloudflare challenge, and extract cookies
        
        Returns:
            Tuple of (success, cookies_dict)
        """
        try:
            logger.info("🔐 Starting Cloudflare challenge solver...")
            
            # Create enhanced session
            self.session = self.create_enhanced_session()
            
            # Add some randomization to appear more human
            time.sleep(random.uniform(1, 3))
            
            logger.info(f"🌐 Visiting {url} to trigger Cloudflare challenge...")
            
            # Make the request - cloudscraper will handle the challenge
            # Use a custom SSL context to handle certificate issues
            import ssl
            import requests
            
            # Create a custom adapter with modified SSL context
            class SSLAdapter(requests.adapters.HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    kwargs['ssl_context'] = ctx
                    return super().init_poolmanager(*args, **kwargs)
            
            # Mount the custom adapter
            self.session.mount('https://', SSLAdapter())
            
            response = self.session.get(url, timeout=30, verify=False)
            
            # Check if we successfully got through
            if response.status_code == 200:
                logger.info("✅ Successfully passed Cloudflare challenge!")
                
                # Extract all cookies
                self.cookies = dict(self.session.cookies)
                
                # Log cookies found
                logger.info(f"🍪 Found {len(self.cookies)} cookies:")
                for name in self.cookies:
                    logger.info(f"   - {name}: {self.cookies[name][:50]}...")
                
                # Check for essential cookies
                essential_cookies = ['cf_clearance', 'XSRF-TOKEN', '__session']
                found_essential = [c for c in essential_cookies if c in self.cookies]
                
                if 'cf_clearance' in self.cookies:
                    logger.info("✅ Found cf_clearance cookie - challenge solved!")
                    return True, self.cookies
                else:
                    logger.warning("⚠️ No cf_clearance cookie found - may need manual intervention")
                    return True, self.cookies
                    
            else:
                logger.error(f"❌ Failed to pass challenge. Status: {response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                return False, {}
                
        except cloudscraper.exceptions.CloudflareChallengeError as e:
            logger.error(f"❌ Cloudflare challenge failed: {e}")
            return False, {}
            
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False, {}
    
    def save_cookies(self, filepath: str = "cache/sessions/plc_auction_session.json"):
        """Save captured cookies to file"""
        if not self.cookies:
            logger.warning("⚠️ No cookies to save")
            return False
            
        try:
            # Ensure directory exists
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare session data
            session_data = {
                "cookies": self.cookies,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "metadata": {
                    "solver": "cloudscraper",
                    "method": "enhanced"
                }
            }
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(session_data, f, indent=2)
                
            logger.info(f"💾 Saved cookies to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save cookies: {e}")
            return False
    
    def update_cars_py(self):
        """Update the Glovis/cars.py file with fresh cookies"""
        if not self.cookies:
            logger.warning("⚠️ No cookies to update")
            return False
            
        try:
            # Generate the Python code
            code_lines = ['import requests\n\n', 'cookies = {\n']
            
            for key, value in self.cookies.items():
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
            
            if "XSRF-TOKEN" in self.cookies:
                code_lines.append(f'    "x-xsrf-token": "{self.cookies["XSRF-TOKEN"]}",\n')
            
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
            
            # Write to file
            with open('Glovis/cars.py', 'w') as f:
                f.writelines(code_lines)
                
            logger.info("✅ Updated Glovis/cars.py with fresh cookies")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update cars.py: {e}")
            return False


def main():
    """Test the enhanced Cloudflare solver"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    solver = PLCCloudflareSolver()
    
    # Try to solve the challenge
    success, cookies = solver.solve_challenge_and_get_cookies()
    
    if success and cookies:
        # Save cookies
        solver.save_cookies()
        solver.update_cars_py()
        
        print("\n🎉 Successfully captured cookies!")
        print("Now you can test the API with: python test_plc_rum.py")
    else:
        print("\n❌ Failed to capture cookies automatically")
        print("You may need to capture them manually using the browser")


if __name__ == "__main__":
    main()