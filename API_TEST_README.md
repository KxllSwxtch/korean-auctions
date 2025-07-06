# AutoBaza API Comprehensive Test Suite

This test suite provides comprehensive testing for the AutoBaza Parser API to ensure production readiness.

## Features

- 🔍 **Comprehensive Coverage**: Tests all auction endpoints, filters, search, and special features
- 🚀 **Performance Testing**: Measures response times and concurrent request handling
- 🔒 **Security Checks**: Tests CORS, error handling, and data sanitization
- 📊 **Detailed Reporting**: Generates both console output and JSON reports
- 🎯 **Multiple Test Modes**: Quick, Full, and Production modes

## Installation

```bash
pip install -r test_requirements.txt
```

## Usage

### Basic Usage

```bash
# Test local development server
python test_api_comprehensive.py

# Test specific server
python test_api_comprehensive.py --url http://api.example.com
```

### Test Modes

```bash
# Quick mode - Basic connectivity and core endpoints only
python test_api_comprehensive.py --mode quick

# Full mode (default) - All endpoints and features
python test_api_comprehensive.py --mode full

# Production mode - Includes security and production readiness checks
python test_api_comprehensive.py --mode production
```

### Additional Options

```bash
# Set custom timeout (default: 30 seconds)
python test_api_comprehensive.py --timeout 60

# Full example
python test_api_comprehensive.py --url https://api.autobaza.com --mode production --timeout 45
```

## Test Categories

### 1. Basic Connectivity Tests
- Root endpoint (`/`)
- Health check (`/health`)
- API documentation (`/docs`)

### 2. Per-Auction Tests
For each auction (Autohub, Lotte, KCar, Glovis, HeyDealer, SSANCAR):
- **Car List Tests**: Default lists, pagination, response structure
- **Filter Tests**: Manufacturers, models, generations
- **Search Tests**: Basic and advanced search functionality
- **Special Endpoints**: Test data, stats, cache management

### 3. Cross-Auction Tests
- API structure consistency
- Common field validation
- Error format consistency

### 4. Performance Tests
- Sequential request timing
- Concurrent request handling
- Response time analysis

### 5. Production Readiness Tests
- CORS configuration
- Error message sanitization
- API versioning
- Rate limiting detection

## Output

### Console Output
Color-coded results with:
- ✅ **PASSED**: Test successful
- ❌ **FAILED**: Test failed
- ⚠️ **WARNING**: Test passed with concerns
- ⏭️ **SKIPPED**: Test not applicable

### JSON Report
Detailed report saved as `api_test_report_YYYYMMDD_HHMMSS.json` containing:
- Test summary statistics
- Individual test results with timings
- Performance metrics
- Production readiness assessment

## Interpreting Results

### Success Criteria
- **Production Ready**: 0 failures, ≤3 warnings
- **Needs Attention**: 0 failures, >3 warnings
- **Not Ready**: Any failures

### Common Issues and Solutions

1. **Authentication Failures**
   - Ensure credentials are configured in the API
   - Check session persistence

2. **Slow Response Times**
   - Review database queries
   - Implement caching
   - Consider pagination limits

3. **CORS Issues**
   - Configure allowed origins for production
   - Don't use wildcard (*) in production

4. **Missing Rate Limiting**
   - Implement rate limiting for production
   - Consider per-IP and per-user limits

## Example Output

```
================================================================================
AutoBaza API Comprehensive Test Suite
Mode: PRODUCTION | Base URL: http://localhost:8000
================================================================================

Testing Basic Connectivity
----------------------------------------
[PASSED] Root Endpoint (0.05s)
[PASSED] Health Check (0.03s)
[PASSED] API Documentation (0.04s)

Testing LOTTE Auction
----------------------------------------
  Testing Car Lists
[PASSED] lotte Car List (1.23s)
  └─ Found cars/data in response
[PASSED] lotte Pagination (limit) (0.89s)

  Testing Filters
[PASSED] lotte Manufacturers (0.45s)
  └─ Found 37 manufacturers

... (more tests) ...

================================================================================
TEST REPORT SUMMARY
================================================================================

Total Tests: 45
Duration: 23.45 seconds

Results:
  Passed: 42
  Failed: 0
  Warnings: 3
  Skipped: 0

Success Rate: 93.3%

Production Readiness:
  ⚠️  CORS Configuration: CORS allows all origins - consider restricting in production
  ⚠️  Rate Limiting: No rate limiting detected - consider implementing for production

RECOMMENDATION:
⚠️  API is functional but has some warnings to address before production.
```

## CI/CD Integration

Add to your CI/CD pipeline:

```yaml
# GitHub Actions example
- name: Run API Tests
  run: |
    python test_api_comprehensive.py --mode production --url ${{ secrets.API_URL }}
```

## Contributing

When adding new endpoints to the API, please update the test suite:
1. Add endpoint to relevant auction test method
2. Include filter/search tests if applicable
3. Update documentation