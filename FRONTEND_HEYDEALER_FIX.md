# Frontend HeyDealer Filter Fix Guide

## Overview

This guide outlines the necessary changes to fix HeyDealer auction filters in the Frontend. The main issue is that HeyDealer API does not support `model_group` parameter for searching cars, which causes incorrect filtering results.

## Current Issues

1. **Model Group Filtering Not Working**: When users select Brand > Model > Generation and search, the API ignores the model selection because HeyDealer doesn't support the `model_group` parameter.
2. **Incorrect API Parameters**: The Frontend is sending `model_group` which is not recognized by HeyDealer's search API.
3. **UI Flow Mismatch**: The current UI allows searching with just Brand + Model, but HeyDealer requires Brand + Generation (what they call "model").

## Technical Background

### HeyDealer Filter Hierarchy
```
Brand (e.g., KIA - 2oV0gK)
  └── Model Group (e.g., Mohave - lMgGzM) ← NOT supported for search
       └── Generation/Model (e.g., Mohave The Master - apzYwo) ← Required for search
            └── Grade/Configuration (e.g., specific trim - hash_id)
```

### Supported Search Parameters
- ✅ `brand` - Brand hash_id
- ❌ `model_group` - NOT supported by HeyDealer
- ✅ `model` - Generation hash_id (confusingly named "model")
- ✅ `grade` - Configuration hash_id
- ✅ `fuel` - Fuel type
- ✅ `wheel_drive` - Array of drive types (e.g., ["2WD", "4WD"])
- ✅ `min_year`, `max_year` - Year range
- ✅ `min_mileage`, `max_mileage` - Mileage range

## Required Frontend Changes

### 1. Remove model_group from Search Parameters

**In API utility functions:**
```javascript
// REMOVE this parameter from search requests
model_group: selectedModelGroup,

// KEEP these parameters
brand: selectedBrand,
model: selectedGeneration, // This is actually the generation ID
grade: selectedGrade,
```

### 2. Update UI Filter Flow

**Current Flow (Incorrect):**
```
Brand → Model Group → [Optional] Generation → Search
```

**New Flow (Correct):**
```
Brand → Model Group → [REQUIRED] Generation → Search
```

### 3. Disable Search Until Generation is Selected

```javascript
// Example implementation
const canSearch = () => {
  if (!selectedBrand) return false;
  if (!selectedModelGroup) return true; // Can search with just brand
  if (selectedModelGroup && !selectedGeneration) return false; // MUST select generation
  return true;
};

// Disable search button
<button disabled={!canSearch()}>Search</button>
```

### 4. Update Filter Labels

To avoid confusion, consider updating the UI labels:
- "Model" → "Model Series" (for model_group)
- "Generation" → "Model Generation" (for model/generation)

### 5. Fix wheel_drive Parameter

The `wheel_drive` parameter must be sent as an array, not a string:

```javascript
// WRONG
wheel_drive: "2WD,4WD"

// CORRECT
wheel_drive: ["2WD", "4WD"]
```

### 6. Remove model_group from API Calls

Update all HeyDealer API calls to remove the `model_group` parameter:

```javascript
// Search cars endpoint
const searchParams = {
  page: currentPage,
  brand: filters.brand,
  // model_group: filters.modelGroup, // REMOVE THIS LINE
  model: filters.generation, // Use generation ID instead
  grade: filters.grade,
  fuel: filters.fuel,
  wheel_drive: filters.wheelDrive, // Should be an array
  min_year: filters.minYear,
  max_year: filters.maxYear,
  min_mileage: filters.minMileage,
  // ... other parameters
};
```

## API Endpoints Reference

### 1. Get Brands
```
GET /api/v1/heydealer/filters/brands
```
Returns list of all brands with hash_ids.

### 2. Get Model Groups for Brand
```
GET /api/v1/heydealer/filters/brands/{brand_hash_id}/models
```
Returns model groups for a specific brand.

### 3. Get Generations for Model Group
```
GET /api/v1/heydealer/filters/model-groups/{model_group_hash_id}/generations
```
Returns generations (called "models" in API) for a model group.

### 4. Get Configurations for Generation
```
GET /api/v1/heydealer/filters/models/{model_hash_id}/configurations
```
Returns grade configurations for a specific generation.

### 5. Search Cars
```
GET /api/v1/heydealer/cars/filtered
```
Parameters:
- `brand` (string): Brand hash_id
- `model` (string): Generation hash_id (NOT model_group)
- `grade` (string): Configuration hash_id
- `fuel` (string): Fuel type
- `wheel_drive` (string): Comma-separated drive types (backend converts to array)
- `min_year`, `max_year` (number): Year range
- `min_mileage`, `max_mileage` (number): Mileage range

## Testing Instructions

### Test Case 1: Brand Only Search
1. Select only a brand (e.g., KIA)
2. Click search
3. ✅ Should return all KIA vehicles

### Test Case 2: Brand + Model + Generation Search
1. Select Brand: KIA (2oV0gK)
2. Select Model: Mohave (lMgGzM)
3. Select Generation: Mohave The Master (apzYwo)
4. Click search
5. ✅ Should return only Mohave The Master vehicles

### Test Case 3: Search Button State
1. Select Brand + Model Group
2. ❌ Search button should be disabled
3. Select a Generation
4. ✅ Search button should be enabled

### Test Case 4: Multiple Filters
1. Select Brand: BMW
2. Select appropriate Model and Generation
3. Add filters:
   - Fuel: gasoline
   - Year: 2020-2024
   - Wheel Drive: 2WD, 4WD
4. ✅ Should return filtered results

## Common Mistakes to Avoid

1. **Don't send model_group in search parameters** - It's not supported
2. **Don't allow search with just Brand + Model** - Generation is required
3. **Ensure wheel_drive is handled as array** - Backend expects comma-separated string and converts it
4. **Use correct hash_ids** - They are always 6 characters long

## Example Implementation

```javascript
// Filter state
const [filters, setFilters] = useState({
  brand: null,
  modelGroup: null, // For UI navigation only
  generation: null, // This is sent as 'model' to API
  grade: null,
  fuel: null,
  wheelDrive: [],
  minYear: null,
  maxYear: null,
  minMileage: null,
});

// Search function
const searchCars = async () => {
  const params = {
    page: 1,
    brand: filters.brand,
    model: filters.generation, // Note: 'model' param = generation ID
    grade: filters.grade,
    fuel: filters.fuel,
    wheel_drive: filters.wheelDrive.join(','), // Convert array to comma-separated
    min_year: filters.minYear,
    max_year: filters.maxYear,
    min_mileage: filters.minMileage,
  };
  
  // Remove undefined/null parameters
  Object.keys(params).forEach(key => {
    if (params[key] === null || params[key] === undefined || params[key] === '') {
      delete params[key];
    }
  });
  
  const response = await fetch('/api/v1/heydealer/cars/filtered?' + new URLSearchParams(params));
  // Handle response...
};
```

## Support

If you encounter any issues or need clarification:
1. Check the backend logs for detailed error messages
2. Use browser DevTools to inspect actual API requests/responses
3. Refer to the HeyDealer example files in `/backend/HeyDealer/` for API structure reference

## Summary of Changes

1. ✅ Remove `model_group` from all search API calls
2. ✅ Make generation selection mandatory when model group is selected
3. ✅ Update search button state logic
4. ✅ Ensure `wheel_drive` is sent as comma-separated string (backend handles array conversion)
5. ✅ Update UI labels for clarity
6. ✅ Test all filter combinations thoroughly