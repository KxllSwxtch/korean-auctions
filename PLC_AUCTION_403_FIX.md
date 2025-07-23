# PLC Auction (Glovis) 403 Forbidden Fix

## Problem
The PLC Auction API (https://plc.auction) is protected by Cloudflare and requires valid cookies to access. When these cookies expire, the API returns 403 Forbidden errors.

## Solution Implemented

### 1. Enhanced Cookie Management
- Updated `DEFAULT_COOKIES` with fresh values from `Glovis/cars.py`
- Added cookie validation before each request
- Automatic session refresh when cookies are invalid

### 2. Improved Cloudflare Handling
- Updated cloudscraper configuration:
  - Increased delay to 2 seconds to avoid rate limiting
  - Added nodejs interpreter for better challenge solving
  - Enhanced browser fingerprint settings

### 3. Better Error Recovery
- Multi-step retry logic for 403 errors:
  1. First attempt: Update cookies from `cars.py`
  2. Second attempt: Full session refresh
  3. Final retry with new session

### 4. Cookie Validation
- Added `_validate_cookies()` method to check essential cookies:
  - `cf_clearance` - Cloudflare clearance token
  - `XSRF-TOKEN` - CSRF protection token
  - `__session` - Session identifier

## How to Update Cookies When They Expire

### Method 1: Using Browser DevTools
1. Open https://plc.auction/auction in Chrome
2. Open Developer Tools (F12)
3. Go to Network tab
4. Reload the page
5. Find the 'auction' request
6. Right-click → Copy → Copy as cURL (bash)
7. Run the helper script:
   ```bash
   python update_plc_cookies.py
   ```
8. Paste the cURL command and press Enter twice

### Method 2: Manual Cookie Update
1. Get cookies from browser DevTools → Application → Cookies
2. Update `DEFAULT_COOKIES` in `plc_auction_service.py`
3. Update cookies in `Glovis/cars.py`

### Method 3: API Endpoint
Use the `/api/v1/glovis/update-cookies` endpoint:
```bash
curl -X POST http://localhost:8000/api/v1/glovis/update-cookies \
  -H "Content-Type: application/json" \
  -d '{
    "cf_clearance": "new_cloudflare_token",
    "XSRF-TOKEN": "new_xsrf_token",
    "__session": "new_session_token"
  }'
```

## Testing

Run the test script to verify the fix:
```bash
cd backend
source venv/bin/activate
python test_plc_auction_fix.py
```

## Files Modified
1. `/backend/app/services/plc_auction_service.py` - Main service improvements
2. `/backend/Glovis/cars.py` - Updated cookies storage
3. `/backend/update_plc_cookies.py` - Helper script for cookie updates
4. `/backend/test_plc_auction_fix.py` - Test script

## Key Improvements
- ✅ Automatic cookie validation before requests
- ✅ Better Cloudflare challenge handling
- ✅ Multi-step retry logic for 403 errors
- ✅ Cookie refresh from multiple sources
- ✅ Helper scripts for easy cookie updates

## Monitoring
- Check logs for cookie validation warnings
- Monitor 403 error frequency
- Update cookies when seeing repeated 403s