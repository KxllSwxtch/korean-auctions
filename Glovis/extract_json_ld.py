import re
import json
from bs4 import BeautifulSoup

# Read the HTML file
with open('cars.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Parse HTML
soup = BeautifulSoup(html_content, 'html.parser')

# Find all script tags with type="application/ld+json"
json_ld_scripts = soup.find_all('script', type='application/ld+json')

print(f"Found {len(json_ld_scripts)} JSON-LD scripts\n")

# Process each JSON-LD script
for i, script in enumerate(json_ld_scripts):
    try:
        # Clean and parse JSON
        json_text = script.string.strip()
        # Remove escaped slashes
        json_text = json_text.replace('\/', '/')
        data = json.loads(json_text)
        
        print(f"=== JSON-LD Script {i+1} ===")
        print(f"Type: {data.get('@type', 'Unknown')}")
        
        # Check if this is the Product with offers
        if data.get('@type') == 'Product' and 'offers' in data:
            offers = data['offers']
            print(f"Name: {data.get('name')}")
            print(f"Offer Type: {offers.get('@type')}")
            print(f"Price Range: ${offers.get('lowPrice')} - ${offers.get('highPrice')}")
            print(f"Currency: {offers.get('priceCurrency')}")
            print(f"Total Offers: {offers.get('offerCount')}")
            
            # Extract individual offers
            if 'offers' in offers:
                individual_offers = offers['offers']
                print(f"\nFound {len(individual_offers)} individual car offers in the array:")
                
                # Save the complete JSON structure
                with open('cars_json_ld_complete.json', 'w', encoding='utf-8') as out:
                    json.dump(data, out, indent=2, ensure_ascii=False)
                print("\nComplete JSON-LD data saved to: cars_json_ld_complete.json")
                
                # Display car details
                print("\nCar Details:")
                for j, offer in enumerate(individual_offers):
                    car = offer.get('itemOffered', {})
                    print(f"\n{j+1}. {car.get('name', 'Unknown')}:")
                    print(f"   - Price: ${offer.get('price')}")
                    print(f"   - Brand: {car.get('brand')}")
                    print(f"   - Model: {car.get('model')}")
                    print(f"   - Year: {car.get('productionDate')}")
                    print(f"   - Color: {car.get('color')}")
                    print(f"   - Fuel: {car.get('fuelType')}")
                    print(f"   - Transmission: {car.get('vehicleTransmission')}")
                    mileage = car.get('mileageFromOdometer', {})
                    print(f"   - Mileage: {mileage.get('value')} {mileage.get('unitCode')}")
                    print(f"   - Image: {car.get('image')}")
                
                # Save individual offers to separate file
                with open('cars_offers_only.json', 'w', encoding='utf-8') as out:
                    json.dump(individual_offers, out, indent=2, ensure_ascii=False)
                print(f"\nIndividual offers saved to: cars_offers_only.json")
                
        elif data.get('@type') == 'Organization':
            print(f"Organization: {data.get('name')}")
            print(f"URL: {data.get('url')}")
            
        elif data.get('@type') == 'BreadcrumbList':
            print("Breadcrumb navigation found")
            
        print("\n")
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON-LD script {i+1}: {e}")
        print("Raw content preview:", script.string[:200] if script.string else "No content")