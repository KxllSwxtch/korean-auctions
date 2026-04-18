#!/usr/bin/env python3
"""Check BMW model codes from the API"""

import json

import requests

BASE_URL = "https://korean-auctions-1.onrender.com"

# Get BMW models
response = requests.get(f"{BASE_URL}/api/v1/ssancar/models/BMW")
data = response.json()

print("BMW Models from API:")
print(f"Total models: {len(data.get('models', []))}")
print("\nModel details:")

for i, model in enumerate(data.get("models", [])):
    print(f"{i + 1}. {model}")

# Check if models are objects or strings
if data.get("models"):
    first_model = data["models"][0]
    print(f"\nFirst model type: {type(first_model)}")
    print(f"First model value: {first_model}")
