#!/usr/bin/env python3
"""
Discover correct SSANCAR model codes by testing actual searches.
The API returns incorrect codes, so we need to find the actual working codes.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_URL = "https://korean-auctions-1.onrender.com"

# Known working codes (verified)
KNOWN_CODES = {
    "BMW": {
        "3 Series": 692,
        "5 Series": 694,
    },
    "벤츠": {  # Mercedes-Benz
        "C-Class": 655,  # From user's URL
    },
}


def get_manufacturers():
    """Get all manufacturers from the API"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/ssancar/manufacturers", timeout=10)
        data = response.json()
        if data.get("success"):
            return data["manufacturers"]
    except Exception as e:
        logger.error(f"Error fetching manufacturers: {e}")
    return []


def get_models(manufacturer_code: str):
    """Get all models for a manufacturer from the API"""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/ssancar/models/{manufacturer_code}", timeout=10
        )
        data = response.json()
        if data.get("success"):
            return data["models"]
    except Exception as e:
        logger.error(f"Error fetching models for {manufacturer_code}: {e}")
    return []


def test_model_code(
    manufacturer: str, code: int, week_no: str = "2"
) -> Tuple[bool, int]:
    """
    Test if a model code returns results for a manufacturer.
    Returns (success, car_count)
    """
    try:
        payload = {
            "weekNo": week_no,
            "maker": manufacturer,
            "model": str(code),
            "yearFrom": "2000",
            "yearTo": "2025",
            "priceFrom": "0",
            "priceTo": "200000",
            "mileageFrom": "0",
            "mileageTo": "500000",
            "list": "5",
            "pages": "0",
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/ssancar/search", json=payload, timeout=10
        )

        data = response.json()
        if data.get("success"):
            car_count = data.get("total_count", 0)
            if car_count > 0:
                # Get first car's model name for verification
                cars = data.get("cars", [])
                if cars:
                    model_name = cars[0].get("model", "")
                    return True, car_count, model_name
            return False, 0, ""
    except Exception as e:
        logger.debug(f"Error testing code {code} for {manufacturer}: {e}")
    return False, 0, ""


def find_model_code_range(
    manufacturer: str, start: int = 600, end: int = 800
) -> Dict[int, str]:
    """
    Find all working model codes in a range for a manufacturer.
    Returns a dict of {code: model_name}
    """
    working_codes = {}
    logger.info(f"Scanning codes {start}-{end} for {manufacturer}")

    # Test codes in parallel for speed
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(test_model_code, manufacturer, code): code
            for code in range(start, end)
        }

        for future in as_completed(futures):
            code = futures[future]
            try:
                success, count, model_name = future.result()
                if success:
                    working_codes[code] = model_name
                    logger.info(
                        f"✅ Found: {manufacturer} code {code} -> {model_name} ({count} cars)"
                    )
            except Exception as e:
                logger.error(f"Error testing code {code}: {e}")

    return working_codes


def discover_model_codes_for_manufacturer(
    manufacturer_code: str, manufacturer_name: str
) -> Dict:
    """
    Discover all model codes for a manufacturer.
    """
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Processing: {manufacturer_code} ({manufacturer_name})")
    logger.info(f"{'=' * 60}")

    # Get models from API
    api_models = get_models(manufacturer_code)
    logger.info(f"API returned {len(api_models)} models")

    # Find actual working codes
    # Different manufacturers use different code ranges
    code_ranges = [
        (600, 750),  # Common range for many brands
        (500, 600),  # Some brands use lower codes
        (750, 850),  # Some use higher codes
    ]

    all_working_codes = {}
    for start, end in code_ranges:
        working_codes = find_model_code_range(manufacturer_code, start, end)
        all_working_codes.update(working_codes)
        if len(all_working_codes) >= len(api_models) * 0.8:  # Found most models
            break

    # Match API models with discovered codes
    mapping = {}
    for api_model in api_models:
        api_code = api_model["no"]
        api_name = api_model.get("e_name", api_model["name"])

        # Try to find matching working code
        matched_code = None
        for code, model_name in all_working_codes.items():
            # Check if model names match (fuzzy matching)
            if (
                api_name.lower() in model_name.lower()
                or model_name.lower() in api_name.lower()
                or api_model["name"] in model_name
            ):
                matched_code = code
                break

        if matched_code:
            mapping[api_code] = {
                "actual_code": str(matched_code),
                "api_name": api_name,
                "korean_name": api_model["name"],
                "actual_name": all_working_codes[matched_code],
            }
            logger.info(
                f"  Mapped: {api_name} - API:{api_code} -> Actual:{matched_code}"
            )
        else:
            logger.warning(f"  No match found for: {api_name} (API:{api_code})")

    return {
        "manufacturer": manufacturer_code,
        "manufacturer_name": manufacturer_name,
        "api_models_count": len(api_models),
        "discovered_codes": len(all_working_codes),
        "mapped_count": len(mapping),
        "mappings": mapping,
        "all_working_codes": {str(k): v for k, v in all_working_codes.items()},
    }


def discover_all_model_codes():
    """
    Discover model codes for all manufacturers.
    """
    # Priority manufacturers to process first
    priority_manufacturers = ["BMW", "벤츠", "아우디", "기아", "현대"]

    manufacturers = get_manufacturers()
    logger.info(f"Found {len(manufacturers)} manufacturers")

    # Sort manufacturers with priority ones first
    sorted_manufacturers = []
    for m in manufacturers:
        if m["code"] in priority_manufacturers:
            sorted_manufacturers.insert(0, m)
        else:
            sorted_manufacturers.append(m)

    all_mappings = {}

    for manufacturer in sorted_manufacturers[:10]:  # Process first 10 for testing
        code = manufacturer["code"]
        name = manufacturer["name"]

        # Skip if we don't have many cars for this manufacturer
        if code in ["람보르기니", "맥라렌", "부가티"]:  # Exotic brands with few cars
            logger.info(f"Skipping exotic brand: {code}")
            continue

        result = discover_model_codes_for_manufacturer(code, name)
        all_mappings[code] = result

        # Save progress after each manufacturer
        with open("ssancar_model_mappings_progress.json", "w", encoding="utf-8") as f:
            json.dump(all_mappings, f, ensure_ascii=False, indent=2)

        # Rate limiting
        time.sleep(2)

    return all_mappings


def generate_typescript_mappings(mappings: Dict) -> str:
    """
    Generate TypeScript code for the mappings.
    """
    ts_code = """// Auto-generated SSANCAR model code mappings
// Generated on: {date}

export const SSANCAR_MODEL_MAPPINGS = {{
""".format(date=time.strftime("%Y-%m-%d %H:%M:%S"))

    for manufacturer, data in mappings.items():
        if not data.get("mappings"):
            continue

        # Convert manufacturer code for TypeScript
        ts_manufacturer = (
            manufacturer.replace("벤츠", "Mercedes")
            .replace("기아", "Kia")
            .replace("현대", "Hyundai")
        )

        ts_code += f"  '{ts_manufacturer}': {{\n"
        for api_code, mapping in data["mappings"].items():
            actual_code = mapping["actual_code"]
            api_name = mapping["api_name"]
            ts_code += f'    "{api_code}": "{actual_code}", // {api_name}\n'
        ts_code += "  },\n"

    ts_code += "};\n"
    return ts_code


def main():
    """Main function to discover all model codes"""
    logger.info("Starting SSANCAR model code discovery...")

    # Quick test with known codes
    logger.info("\nTesting known codes...")
    test_success, count, _ = test_model_code("BMW", 692)  # BMW 3 Series
    logger.info(
        f"BMW code 692 (3 Series): {'✅ Working' if test_success else '❌ Failed'} ({count} cars)"
    )

    test_success, count, _ = test_model_code("BMW", 694)  # BMW 5 Series
    logger.info(
        f"BMW code 694 (5 Series): {'✅ Working' if test_success else '❌ Failed'} ({count} cars)"
    )

    test_success, count, _ = test_model_code("벤츠", 655)  # Mercedes C-Class
    logger.info(
        f"Mercedes code 655 (C-Class): {'✅ Working' if test_success else '❌ Failed'} ({count} cars)"
    )

    # Discover all codes
    logger.info("\nDiscovering all model codes...")
    all_mappings = discover_all_model_codes()

    # Save results
    output_file = "ssancar_model_mappings.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_mappings, f, ensure_ascii=False, indent=2)
    logger.info(f"\n✅ Saved mappings to {output_file}")

    # Generate TypeScript code
    ts_code = generate_typescript_mappings(all_mappings)
    ts_file = "ssancar_model_mappings.ts"
    with open(ts_file, "w", encoding="utf-8") as f:
        f.write(ts_code)
    logger.info(f"✅ Generated TypeScript mappings in {ts_file}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for manufacturer, data in all_mappings.items():
        logger.info(
            f"{manufacturer}: {data['mapped_count']}/{data['api_models_count']} models mapped"
        )


if __name__ == "__main__":
    main()
