# Lotte Auction Stability Implementation Guide

## Status: 30% Complete

### ✅ Completed
- [x] Base classes created (BaseAuctionParser, BaseAuctionService, base error models)
- [x] Lotte parser updated to inherit from BaseAuctionParser
- [x] SELECTOR_FALLBACKS dictionary added to Lotte parser
- [x] parse_auction_date() method updated with fallback system

### 🔄 Remaining Work

## 1. Complete Lotte Parser Updates (~1-2 hours)

### Files to Update
- `/korean-auctions/app/parsers/lotte_parser.py`

### Pattern to Follow

For EVERY parsing method in lotte_parser.py:

#### Step 1: Add _reset_stats() at method start
```python
def parse_cars_list(self, html_content: str):
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        self._reset_stats()  # ADD THIS LINE

        # ... rest of code
```

#### Step 2: Replace single .find() calls with _find_with_fallbacks()

**Before (FRAGILE):**
```python
table = soup.find("table", class_="tbl-t02")
if not table:
    # fallback logic here
```

**After (ROBUST):**
```python
table = self._find_with_fallbacks(soup, "table")
self._track_extraction("table", table)
if not table:
    self._save_debug_html(html_content, "unknown", "table_not_found")
    return []
```

#### Step 3: Track ALL field extractions

After extracting each field:
```python
car_name = self._find_with_fallbacks(soup, "car_name")
self._track_extraction("car_name", car_name)

price = self._find_with_fallbacks(soup, "price")
self._track_extraction("price", price)

# etc for all fields
```

#### Step 4: Add validation before returning

At end of parsing:
```python
# Get missing fields
missing, has_all = self._get_missing_fields([
    "car_name", "price", "table"  # List critical fields
])

if not has_all:
    logger.warning(f"Missing fields: {missing}")
    self._save_debug_html(html_content, car_id, "missing_fields")

# Return with extraction stats
return {
    "cars": cars,
    "extraction_stats": self.extraction_stats,
    "missing_fields": missing if not has_all else None
}
```

### Methods That Need Updating

1. **parse_cars_list()** - Line 141
   - Replace table.find() with fallbacks
   - Add tracking for table, rows, each car field

2. **parse_car_detail()** - Find this method
   - Add fallbacks for all detail fields
   - Track each field extraction

3. **Any other parse_* methods**
   - Apply same pattern

### Expanding SELECTOR_FALLBACKS

Add more field configurations:
```python
SELECTOR_FALLBACKS = {
    # Existing...
    "auction_date_block": [...],
    "table": [...],
    "car_name": [...],
    "price": [...],

    # ADD MORE:
    "year": [
        ("td", "year-cell", None),
        ("td", "year", None),
        ("span", "car-year", None),
    ],
    "mileage": [
        ("td", "mileage-cell", None),
        ("td", "milg", None),
        ("span", "mileage", None),
    ],
    "transmission": [
        ("td", "trans-cell", None),
        ("td", "transmission", None),
        ("span", "trans-type", None),
    ],
    # ... add all critical fields from Lotte HTML
}
```

---

## 2. Update Lotte Service (~1-2 hours)

### File to Update
- `/korean-auctions/app/services/lotte_service.py`

### Step 1: Update class definition and __init__

**Find current code:**
```python
class LotteService:
    def __init__(self):
        self.session = requests.Session()
        self.authenticated = False
        # ... other init code
```

**Replace with:**
```python
from app.services.base_auction_service import BaseAuctionService

class LotteService(BaseAuctionService):
    def __init__(self):
        super().__init__("Lotte Service")

        # Remove these lines (now in base class):
        # - self.session = requests.Session()
        # - self.authenticated = False
        # - self.session_created_at = ...
        # - self.consecutive_failures = ...

        # Keep Lotte-specific init:
        self.username = "your_username"
        self.password = "your_password"
        # etc...
```

### Step 2: Add session refresh to request methods

Find ALL methods that make HTTP requests:
- `get_cars()`
- `fetch_car_detail()`
- Any others

**Before each request, add:**
```python
def get_cars(self, page: int = 1):
    # ADD THIS CHECK FIRST:
    if not self._refresh_session_if_needed():
        return {
            "success": False,
            "error_type": "authentication_failed",
            "message": "Failed to refresh session"
        }

    # Existing request code...
    try:
        response = self.session.get(url)

        # ADD ON SUCCESS:
        self._record_success()
        return result

    except Exception as e:
        # ADD ON FAILURE:
        self._record_failure(e)
        raise
```

### Step 3: Update error responses

Import error types:
```python
from app.models.base_auction import AuctionErrorType, create_error_response
```

Replace generic errors:
```python
# Before:
return {"success": False, "message": "Error"}

# After:
return create_error_response(
    error_type=AuctionErrorType.PARSING_FAILED,
    message="Failed to parse car data",
    missing_fields=["car_name", "price"]
)
```

---

## 3. Update Lotte Models (~30 min)

### File to Update
- `/korean-auctions/app/models/lotte.py`

### Step 1: Import base error types

```python
from typing import Optional, List, Dict
from app.models.base_auction import (
    AuctionErrorType,
    BaseDetailResponse
)
```

### Step 2: Update response models

Find models like `LotteDetailResponse` and add:

```python
class LotteDetailResponse(BaseModel):
    car: Optional[LotteCarDetail]
    success: bool
    message: Optional[str]
    source_url: Optional[str]

    # ADD THESE:
    error_type: Optional[AuctionErrorType] = None
    missing_fields: Optional[List[str]] = None
    extraction_stats: Optional[Dict[str, bool]] = None
```

Or inherit from BaseDetailResponse:
```python
class LotteDetailResponse(BaseDetailResponse):
    car: Optional[LotteCarDetail]
    # Other Lotte-specific fields
```

---

## 4. Update Lotte Routes (~30 min)

### File to Update
- `/korean-auctions/app/routes/lotte.py`

### Step 1: Import error utilities

```python
from app.models.base_auction import (
    AuctionErrorType,
    get_http_status_for_error
)
```

### Step 2: Update error handling

**Find error handling code like:**
```python
if not result.success:
    raise HTTPException(
        status_code=404,
        detail=result.message
    )
```

**Replace with:**
```python
if not result.success:
    # Get appropriate HTTP status based on error type
    status_code = get_http_status_for_error(
        result.error_type or AuctionErrorType.UNKNOWN_ERROR
    )

    raise HTTPException(
        status_code=status_code,
        detail={
            "error": "Failed to get car details",
            "message": result.message,
            "error_type": result.error_type,
            "missing_fields": result.missing_fields,
            "car_id": car_id
        }
    )
```

---

## 5. Update Lotte Frontend (~30 min)

### Files to Update
- `/autobazaapp/lib/types/lotte.ts`
- `/autobazaapp/lib/utils/lotteApi.ts` (if exists)

### Update Types

```typescript
// lotte.ts
export interface LotteDetailResponse {
  car: LotteCarDetail
  success: boolean
  message: string
  source_url: string

  // ADD THESE:
  error_type?: string
  missing_fields?: string[]
  extraction_stats?: Record<string, boolean>
}
```

### Update API Client

```typescript
// lotteApi.ts
if (!response.ok) {
  const errorData = await response.json()
  const errorType = errorData.detail?.error_type || errorData.error_type

  // User-friendly messages
  let userMessage = errorData.message

  if (errorType === "car_not_found") {
    userMessage = "Автомобиль не найден или был удален с аукциона."
  } else if (errorType === "authentication_failed") {
    userMessage = "Ошибка авторизации. Попробуйте позже."
  } else if (errorType === "parsing_failed") {
    userMessage = "Ошибка обработки данных с аукциона."
  } // ... other error types

  throw new Error(userMessage)
}
```

---

## 6. Testing (~1 hour)

### Test 1: Parser Fallback System

```bash
cd korean-auctions
source venv/bin/activate
python -c "
from app.parsers.lotte_parser import LotteParser
parser = LotteParser()

# Test with sample HTML
html = '<table class=\"tbl-t02\"><tbody><tr>test</tr></tbody></table>'
result = parser.parse_cars_list(html)

print('Extraction stats:', parser.extraction_stats)
print('Fields tracked:', parser.extraction_stats.keys())
"
```

### Test 2: Session Management

```bash
python -c "
from app.services.lotte_service import LotteService
service = LotteService()

# Check session stats
stats = service._get_session_stats()
print('Session stats:', stats)
print('Session age:', stats['session_age_minutes'])
print('Consecutive failures:', stats['consecutive_failures'])
"
```

### Test 3: API Endpoint

```bash
# Test via curl
curl -X GET "http://localhost:8000/api/v1/lotte/cars?page=1" \
  -H "Content-Type: application/json" | jq

# Check for:
# - extraction_stats in response
# - error_type if error occurs
# - missing_fields if parsing incomplete
```

### Test 4: Frontend

```bash
cd autobazaapp
npm run dev

# Navigate to Lotte page
# Try accessing car that doesn't exist
# Should see user-friendly error message based on error_type
```

---

## Checklist Before Completion

- [ ] All parse methods use `_reset_stats()`
- [ ] All `.find()` calls replaced with `_find_with_fallbacks()`
- [ ] All fields tracked with `_track_extraction()`
- [ ] LotteService inherits from BaseAuctionService
- [ ] All request methods call `_refresh_session_if_needed()`
- [ ] Success/failure recorded with `_record_success/failure()`
- [ ] Response models include error_type, missing_fields, extraction_stats
- [ ] Routes use `get_http_status_for_error()`
- [ ] Frontend types include new error fields
- [ ] Frontend shows user-friendly error messages
- [ ] All tests pass

---

## Quick Reference: Base Class Methods

### BaseAuctionParser
```python
self._reset_stats()  # Reset before parsing
self._find_with_fallbacks(soup, "field_name")  # Find with fallbacks
self._track_extraction("field", value)  # Track extraction
self._get_missing_fields(["field1", "field2"])  # Validate
self._save_debug_html(html, id, reason)  # Save for debug
self._get_extraction_summary()  # Get stats
```

### BaseAuctionService
```python
self._is_session_expired()  # Check expiry
self._refresh_session_if_needed()  # Auto-refresh
self._record_success()  # Track success
self._record_failure(exception)  # Track failure
self._get_session_stats()  # Get statistics
self._should_alert()  # Check if needs attention
```

---

## Expected Time to Complete

- Parser updates: 1-2 hours
- Service updates: 1-2 hours
- Model updates: 30 minutes
- Route updates: 30 minutes
- Frontend updates: 30 minutes
- Testing: 1 hour

**Total: 4-6 hours** (as estimated)

---

## After Lotte is Complete

This same pattern can be applied to the 8 remaining auctions:
- AutoHub
- SsangCar
- Glovis
- Glovis Detail
- PLC Auction
- Encar
- BikeMart
- HeyDealer

Each should take 2-4 hours following this template!
