#!/usr/bin/env python3
import os
import json
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}

URL = "https://www.komoot.com/discover/Current_location/@37.5049040,127.0640070/tours?sport=touringbicycle&map=true&max_distance=500&pageNumber=1"

def extract_json_from_html(html_content):
    match = re.search(r'kmtBoot\.setProps\("(.*)"\);', html_content)
    if not match:
        match = re.search(r"kmtBoot\.setProps\('(.*)'\);", html_content)
    if match:
        json_str_escaped = match.group(1)
        try:
            return json.loads(f'"{json_str_escaped}"')
        except:
            return None
    return None

print(f"Fetching {URL}...")
resp = requests.get(URL, headers=HEADERS)
html = resp.text

json_data_str = extract_json_from_html(html)
if json_data_str:
    data = json.loads(json_data_str)
    
    queries = data.get("dehydratedQueryClientState", {}).get("queries", [])
    print(f"Found {len(queries)} queries in dehydrated state.")
    
    for i, q in enumerate(queries):
        query_key = q.get("queryKey", [])
        print(f"\nQuery {i} Key: {query_key}")
        
        state_data = q.get("state", {}).get("data", {})
        if not state_data:
            print("  No data in state.")
            continue
            
        if not isinstance(state_data, dict):
            print(f"  Data is not a dict: {type(state_data)}")
            # print(state_data)
            continue

        # Check if this looks like tour data
        embedded = state_data.get("_embedded", {})
        items = embedded.get("items", []) or state_data.get("items", [])
        
        if items:
            print(f"  Found {len(items)} items in this query!")
            first_item = items[0]
            print(f"  Sample item keys: {list(first_item.keys())}")
            if "name" in first_item:
                print(f"  Sample name: {first_item['name']}")
            if "id" in first_item:
                print(f"  Sample ID: {first_item['id']}")
        else:
            print(f"  Data keys: {list(state_data.keys())}")
            # print(json.dumps(state_data, indent=2)[:500]) # Dump start of data if needed

else:
    print("No JSON found.")
