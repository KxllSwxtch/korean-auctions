# AutoHub Frontend Integration Guide

This guide provides comprehensive documentation for integrating AutoHub auction filters into the frontend application.

## Table of Contents
1. [Overview](#overview)
2. [Available Filters](#available-filters)
3. [API Endpoints](#api-endpoints)
4. [Filter Workflow](#filter-workflow)
5. [Request/Response Examples](#requestresponse-examples)
6. [Implementation Guide](#implementation-guide)
7. [Filter Codes Reference](#filter-codes-reference)

## Overview

The AutoHub filter system provides a comprehensive set of filters that mirror the functionality available on the AutoHub website (상세검색 tab). All filters can be used individually or in combination to find specific vehicles.

## Available Filters

### 1. Vehicle Identification
- **Manufacturer** (`manufacturer_code`) - Vehicle manufacturer
- **Model** (`model_code`) - Vehicle model
- **Generation** (`generation_code`) - Model generation
- **Detail** (`detail_code`) - Detailed specification

### 2. Vehicle Characteristics
- **Fuel Type** (`fuel_type`) - Gasoline, Diesel, LPG, Hybrid, Electric
- **Extended Warranty** (`extended_warranty`) - Yes/No/All
- **Year Range** (`year_from`, `year_to`) - Manufacturing year (1990-2025)
- **Mileage Range** (`mileage_from`, `mileage_to`) - In kilometers
- **Price Range** (`price_from`, `price_to`) - In 만원 (10,000 KRW)

### 3. Auction Information
- **Auction Number** (`auction_no`) - Specific auction session
- **Auction Date** (`auction_date`) - Date in YYYY-MM-DD format
- **Auction Code** (`auction_code`) - Unique auction identifier
- **Auction Result** (`auction_result`) - Sold/Unsold/Not Held
- **Lane** (`lane`) - A/B/C/D lanes

### 4. Number Search
- **Search Type** (`search_type`) - Entry number (E) or Car number (C)
- **Search Number** (`search_number`) - 4-digit number
- **Entry Number** (`entry_number`) - Specific entry number
- **Parking Number** (`parking_number`) - Specific parking number
- **Entry Number Assigned** (`entry_no_assigned`) - Yes/No/All
- **Parking Number Assigned** (`parking_no_assigned`) - Yes/No/All

### 5. Additional Filters
- **SOH Diagnosis** (`soh_diagnosis`) - Battery health check (Yes/No/All)
- **Sort Order** (`sort_order`) - Entry/Price/Year/Mileage
- **Pagination** (`page`, `page_size`) - Page control

## API Endpoints

### Base URL
```
https://api.autobaza.com/api/v1/autohub
```

### 1. Get Manufacturers
```http
GET /manufacturers

Response:
{
  "success": true,
  "message": "Список производителей получен успешно",
  "manufacturers": [
    {
      "code": "KA",
      "name": "기아",
      "name_en": "Kia"
    },
    {
      "code": "HD",
      "name": "현대",
      "name_en": "Hyundai"
    },
    ...
  ],
  "total_count": 48,
  "timestamp": "2025-01-08T12:00:00"
}
```

### 2. Get Models
```http
GET /models/{manufacturer_code}

Example: GET /models/KA

Response:
{
  "success": true,
  "message": "Список моделей для KA получен успешно",
  "models": [
    {
      "manufacturer_code": "KA",
      "model_code": "KA01",
      "name": "K5"
    },
    {
      "manufacturer_code": "KA",
      "model_code": "KA02",
      "name": "Sportage"
    },
    ...
  ],
  "manufacturer_code": "KA",
  "total_count": 15,
  "timestamp": "2025-01-08T12:00:00"
}
```

### 3. Get Generations
```http
GET /generations/{model_code}

Example: GET /generations/KA01

Response:
{
  "success": true,
  "message": "Список поколений для KA01 получен успешно",
  "generations": [
    {
      "model_code": "KA01",
      "generation_code": "008",
      "detail_code": "K01",
      "name": "K5 3세대"
    },
    ...
  ],
  "model_code": "KA01",
  "total_count": 5,
  "timestamp": "2025-01-08T12:00:00"
}
```

### 4. Get Auction Sessions
```http
GET /auction-sessions

Response:
{
  "success": true,
  "message": "Список сессий аукциона получен успешно",
  "sessions": [
    {
      "auction_no": "1332",
      "auction_date": "2025-07-09",
      "auction_code": "AC202507020001",
      "auction_title": "안성 2025/07/09 1332회차 경매",
      "is_active": true
    },
    ...
  ],
  "current_session": {...},
  "total_count": 1,
  "timestamp": "2025-01-08T12:00:00"
}
```

### 5. Search Cars
```http
POST /search

Request Body:
{
  "manufacturer_code": "KA",
  "model_code": "KA01",
  "fuel_type": "01",
  "year_from": 2020,
  "year_to": 2023,
  "price_from": 1000,
  "price_to": 3000,
  "mileage_to": 50000,
  "extended_warranty": "Y",
  "page": 1,
  "page_size": 20
}

Response:
{
  "success": true,
  "data": [
    {
      "car_id": "12345",
      "auction_number": "0001",
      "title": "기아 K5 2.0 가솔린",
      "year": 2021,
      "mileage": "35,000",
      "starting_price": 2500,
      "status": "출품등록",
      ...
    },
    ...
  ],
  "total_count": 45,
  "page": 1,
  "limit": 20,
  "parsed_at": "2025-01-08T12:00:00"
}
```

### 6. Get Filter Information
```http
GET /filters/info

Response:
{
  "success": true,
  "message": "Информация о фильтрах получена успешно",
  "filters": {
    "manufacturers": [...],
    "fuel_types": [
      {"code": "", "name": "전체"},
      {"code": "01", "name": "휘발유"},
      {"code": "02", "name": "경유"},
      ...
    ],
    "lanes": [...],
    "auction_results": [...],
    "year_range": {"min": 1990, "max": 2025},
    "mileage_options": [500, 1000, 2000, ...],
    "price_options": [100, 200, 300, ...]
  }
}
```

## Filter Workflow

### Recommended Implementation Flow:

1. **Initialize Filters**
   - Load manufacturers list on component mount
   - Get current auction sessions
   - Load filter options from `/filters/info`

2. **Hierarchical Selection**
   - User selects manufacturer → Load models
   - User selects model → Load generations
   - User selects generation → Enable search

3. **Apply Filters**
   - Collect all selected filter values
   - Send POST request to `/search`
   - Display results with pagination

4. **Reset Filters**
   - Clear all selections
   - Reset to default values
   - Refresh results

## Request/Response Examples

### Example 1: Basic Search
```javascript
// Search for all vehicles
const response = await fetch('/api/v1/autohub/search', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    page: 1,
    page_size: 20
  })
});
```

### Example 2: Filtered Search
```javascript
// Search for Kia K5, 2020-2023, under 50,000km
const response = await fetch('/api/v1/autohub/search', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    manufacturer_code: 'KA',
    model_code: 'KA01',
    year_from: 2020,
    year_to: 2023,
    mileage_to: 50000,
    page: 1,
    page_size: 20
  })
});
```

### Example 3: Complex Filter Combination
```javascript
// Advanced search with multiple filters
const response = await fetch('/api/v1/autohub/search', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    manufacturer_code: 'HD',
    fuel_type: '01', // Gasoline
    year_from: 2021,
    year_to: 2023,
    price_from: 1500,
    price_to: 2500,
    mileage_from: 10000,
    mileage_to: 40000,
    extended_warranty: 'Y',
    soh_diagnosis: 'Y',
    auction_result: 'Y', // Sold
    lane: 'A',
    sort_order: 'price',
    page: 1,
    page_size: 30
  })
});
```

## Implementation Guide

### React Component Example

```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const AutoHubFilters = () => {
  const [manufacturers, setManufacturers] = useState([]);
  const [models, setModels] = useState([]);
  const [generations, setGenerations] = useState([]);
  const [filters, setFilters] = useState({
    manufacturer_code: '',
    model_code: '',
    generation_code: '',
    fuel_type: '',
    year_from: '',
    year_to: '',
    price_from: '',
    price_to: '',
    mileage_from: '',
    mileage_to: '',
    extended_warranty: 'ALL',
    soh_diagnosis: 'ALL',
    page: 1,
    page_size: 20
  });
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load manufacturers on mount
  useEffect(() => {
    loadManufacturers();
  }, []);

  const loadManufacturers = async () => {
    try {
      const response = await axios.get('/api/v1/autohub/manufacturers');
      setManufacturers(response.data.manufacturers);
    } catch (error) {
      console.error('Error loading manufacturers:', error);
    }
  };

  const handleManufacturerChange = async (code) => {
    setFilters({ ...filters, manufacturer_code: code, model_code: '', generation_code: '' });
    setModels([]);
    setGenerations([]);
    
    if (code) {
      try {
        const response = await axios.get(`/api/v1/autohub/models/${code}`);
        setModels(response.data.models);
      } catch (error) {
        console.error('Error loading models:', error);
      }
    }
  };

  const handleModelChange = async (code) => {
    setFilters({ ...filters, model_code: code, generation_code: '' });
    setGenerations([]);
    
    if (code) {
      try {
        const response = await axios.get(`/api/v1/autohub/generations/${code}`);
        setGenerations(response.data.generations);
      } catch (error) {
        console.error('Error loading generations:', error);
      }
    }
  };

  const handleSearch = async () => {
    setLoading(true);
    try {
      const response = await axios.post('/api/v1/autohub/search', filters);
      setResults(response.data.data);
    } catch (error) {
      console.error('Error searching:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="autohub-filters">
      {/* Manufacturer Select */}
      <select 
        value={filters.manufacturer_code} 
        onChange={(e) => handleManufacturerChange(e.target.value)}
      >
        <option value="">Select Manufacturer</option>
        {manufacturers.map(m => (
          <option key={m.code} value={m.code}>
            {m.name} ({m.name_en})
          </option>
        ))}
      </select>

      {/* Model Select */}
      <select 
        value={filters.model_code} 
        onChange={(e) => handleModelChange(e.target.value)}
        disabled={!filters.manufacturer_code}
      >
        <option value="">Select Model</option>
        {models.map(m => (
          <option key={m.model_code} value={m.model_code}>
            {m.name}
          </option>
        ))}
      </select>

      {/* Other filters... */}
      
      <button onClick={handleSearch} disabled={loading}>
        {loading ? 'Searching...' : 'Search'}
      </button>

      {/* Results display */}
      <div className="results">
        {results.map(car => (
          <div key={car.car_id} className="car-item">
            <h3>{car.title}</h3>
            <p>Year: {car.year} | Mileage: {car.mileage}</p>
            <p>Price: {car.starting_price} 만원</p>
          </div>
        ))}
      </div>
    </div>
  );
};
```

## Filter Codes Reference

### Fuel Types
- `""` - All (전체)
- `"01"` - Gasoline (휘발유)
- `"02"` - Diesel (경유)
- `"03"` - LPG
- `"04"` - Hybrid (하이브리드)
- `"05"` - Electric (전기)
- `"06"` - Other (기타)

### Auction Results
- `""` - All (전체)
- `"Y"` - Sold (낙찰 & 후상담낙찰)
- `"N"` - Unsold (유찰 & 낙찰취소)
- `"none"` - Not Held (미실시)

### Lanes
- `""` - All (전체)
- `"A"` - A Lane (A레인)
- `"B"` - B Lane (B레인)
- `"C"` - C Lane (C레인)
- `"D"` - D Lane (D레인)

### Yes/No/All Options
Used for: `extended_warranty`, `soh_diagnosis`, `entry_no_assigned`, `parking_no_assigned`
- `"ALL"` - All (전체)
- `"Y"` - Yes (예)
- `"N"` - No (아니오)

### Sort Orders
- `"entry"` - By entry number (default)
- `"price"` - By price
- `"year"` - By year
- `"milg"` - By mileage

### Search Types
- `"E"` - Entry number (출품번호)
- `"C"` - Car number (차량번호)

## Best Practices

1. **Performance**
   - Cache manufacturer/model lists
   - Implement debouncing for search inputs
   - Use pagination for large result sets

2. **User Experience**
   - Show loading states during API calls
   - Provide clear filter reset functionality
   - Display active filters summary
   - Save filter preferences in localStorage

3. **Error Handling**
   - Handle network errors gracefully
   - Show user-friendly error messages
   - Provide fallback options when filters fail to load

4. **Accessibility**
   - Use proper ARIA labels for filter controls
   - Ensure keyboard navigation works
   - Provide screen reader support

## Notes

- All price values are in 만원 (10,000 KRW units)
- Mileage is in kilometers
- Dates should be in YYYY-MM-DD format
- The API requires authentication for some operations
- Empty filter values are ignored in search
- Maximum page size is 100 items