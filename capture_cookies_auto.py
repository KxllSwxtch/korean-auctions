#!/usr/bin/env python3
"""
Automated cookie capture for PLC Auction using enhanced cloudscraper
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.plc_cloudflare_solver import PLCCloudflareSolver
import logging
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("🤖 PLC Auction Automated Cookie Capture")
    print("=====================================\n")
    
    print("This tool will attempt to automatically capture cookies by solving")
    print("the Cloudflare challenge using enhanced browser emulation.\n")
    
    solver = PLCCloudflareSolver()
    
    print("🔐 Attempting to solve Cloudflare challenge...")
    print("This may take up to 30 seconds...\n")
    
    # Try to solve the challenge
    success, cookies = solver.solve_challenge_and_get_cookies("https://plc.auction/ru")
    
    if success and cookies:
        print(f"\n✅ Successfully captured {len(cookies)} cookies!")
        
        # Save cookies to session file
        if solver.save_cookies():
            print("💾 Saved cookies to session file")
        
        # Update cars.py
        if solver.update_cars_py():
            print("📝 Updated Glovis/cars.py")
        
        print("\n🎉 Cookie capture complete!")
        print("\nNext steps:")
        print("1. Run: source venv/bin/activate")
        print("2. Run: python test_plc_rum.py")
        print("\nThe API should now work with the fresh cookies!")
        
    else:
        print("\n❌ Automated capture failed")
        print("\nThe Cloudflare protection may have changed or require manual solving.")
        print("\nAlternative options:")
        print("1. Try running this script again")
        print("2. Use manual capture: python capture_plc_cookies.py")
        print("3. Try visiting https://plc.auction/ru in your browser first")
        
        # If we have a session, try to get more info
        if solver.session:
            print("\n📋 Debug information:")
            print(f"- Last response status: {getattr(solver.session, 'status_code', 'N/A')}")
            print(f"- Cookies found: {list(solver.cookies.keys()) if solver.cookies else 'None'}")

if __name__ == "__main__":
    main()