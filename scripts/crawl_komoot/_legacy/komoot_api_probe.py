#!/usr/bin/env python3
import re
import json
import requests
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/hal+json,application/json",
    "Referer": "https://www.komoot.com/",
}

START_URL = "https://www.komoot.com/discover/Current_location/@37.5049040,127.0640070/tours?sport=touringbicycle&map=true&max_distance=500&pageNumber=1"

session = requests.Session()
session.headers.update(HEADERS)

def extract_json(html):
    match = re.search(r'kmtBoot\.setProps\("(.*)"\);', html)
    if not match:
        match = re.search(r"kmtBoot\.setProps\('(.*)'\);", html)
    if match:
        try:
            return json.loads(f'"{match.group(1)}"')
        except:
            pass
    return None

print(f"1. Fetching main page: {START_URL}")
resp = session.get(START_URL)
print(f"   Status: {resp.status_code}")

json_data_str = extract_json(resp.text)
if not json_data_str:
    print("   Failed to extract JSON.")
    exit(1)

data = json.loads(json_data_str)
page_data = data.get('page', {})
map_data = page_data.get('_embedded', {}).get('map', {})
bounds = map_data.get('bounds', [])

print(f"2. Extracted Bounds: {bounds}")
# Bounds format: [{'lat': 37.46..., 'lng': 127.00...}, {'lat': 37.54..., 'lng': 127.11...}]
# Convert to simple list [min_lat, min_lng, max_lat, max_lng] ? or other way?

if not bounds:
    print("   No bounds found, using fallback.")
    # Fallback to roughly the location in URL
    # @37.5049040,127.0640070
    bounds = [
        {'lat': 37.4, 'lng': 127.0},
        {'lat': 37.6, 'lng': 127.1}
    ]

# Try to construct bbox string
# Usually min_lng, min_lat, max_lng, max_lat OR min_lat, min_lng, max_lat, max_lng
# Komoot often uses different formats.

# Let's try various endpoints
endpoints = [
    "https://api.komoot.de/v007/discover_tours/",
    "https://api.komoot.de/v007/discover/37.504904,127.064007/elements/"
]

params_variations = [
    # Variation 1: sport and center (radius)
    {
        "sport": "touringbicycle",
        "center": "37.504904,127.064007",
        "max_distance": "500",
        "page": "1"
    },
    # Variation 2: sport and lat/lon
    {
        "sport": "touringbicycle",
        "lat": "37.504904",
        "lon": "127.064007",
        "max_distance": "500"
    },
     # Variation 3: bbox?
     # Assuming bounds[0] is SW and bounds[1] is NE (usually)
     # but let's check values.
     # Komoot JSON: bounds=[{lat: A, lng: B}, {lat: C, lng: D}]
     # A < C usually.
]

if len(bounds) >= 2:
    min_lat = min(b['lat'] for b in bounds)
    max_lat = max(b['lat'] for b in bounds)
    min_lng = min(b['lng'] for b in bounds)
    max_lng = max(b['lng'] for b in bounds)
    
    # Add bbox variations
    params_variations.append({
        "sport": "touringbicycle",
        "bbox": f"{min_lng},{min_lat},{max_lng},{max_lat}"
    })
    params_variations.append({
        "sport": "touringbicycle",
        "bbox": f"{min_lat},{min_lng},{max_lat},{max_lng}"
    })

print(f"3. Probing APIs with session cookies...")

for url in endpoints:
    print(f"
--- Endpoint: {url} ---")
    for i, p in enumerate(params_variations):
        print(f"   Probe {i}: {p}")
        try:
            api_resp = session.get(url, params=p)
            print(f"   Status: {api_resp.status_code}")
            if api_resp.status_code == 200:
                try:
                    res_json = api_resp.json()
                    # Check if we have items
                    items = []
                    if "_embedded" in res_json:
                        items = res_json["_embedded"].get("items", []) or res_json["_embedded"].get("tours", [])
                    
                    print(f"   SUCCESS! Found {len(items)} items.")
                    if items:
                        print(f"   Sample: {items[0].get('name')}")
                        # Save this successful response for inspection
                        with open(f"komoot_api_success_{i}.json", "w") as f:
                            json.dump(res_json, f, indent=2)
                        break # Found a working one for this endpoint
                except:
                    print("   Response not JSON.")
                    print(api_resp.text[:200])
            else:
                print(f"   Error: {api_resp.text[:100]}")
        except Exception as e:
            print(f"   Exception: {e}")
        time.sleep(0.5)
