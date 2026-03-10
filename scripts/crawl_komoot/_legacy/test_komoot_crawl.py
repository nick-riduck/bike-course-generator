#!/usr/bin/env python3
"""
Komoot Crawler Test Script
- Tests metadata extraction and GPX download for 2 items.
- Uses a short delay for quick verification.
"""

import os
import json
import time
import requests
from crawl_komoot import extract_json_from_html, parse_tours_from_json, HEADERS

# Configuration
TEST_URL = "https://www.komoot.com/discover/Current_location/@37.5049040,127.0640070/tours?sport=touringbicycle&map=true&max_distance=500&pageNumber=1"
OUTPUT_DIR = "crawl_data/KOMOOT_TEST"
COOKIE_FILE = "scripts/komoot_cookies.txt"

session = requests.Session()
session.headers.update(HEADERS)

def load_cookies():
    if os.path.exists(COOKIE_FILE):
        print(f"Loading cookies from {COOKIE_FILE}...")
        with open(COOKIE_FILE, 'r') as f:
            for line in f:
                if not line.startswith('#') and line.strip():
                    if '=' in line:
                        key, val = line.strip().split('=', 1)
                        session.cookies.set(key, val)
    else:
        print(f"[INFO] No cookie file found at {COOKIE_FILE}. Testing as guest.")

def download_gpx_test(tour_id, output_path):
    url = f"https://www.komoot.com/api/v007/tours/{tour_id}/download"
    try:
        resp = session.get(url, params={'format': 'gpx'}, timeout=30)
        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(resp.content)
            print(f"  [SUCCESS] GPX downloaded: {output_path} ({len(resp.content)} bytes)")
            return True
        else:
            print(f"  [FAILED] GPX download failed (Status: {resp.status_code}). URL: {url}")
            if resp.status_code == 403:
                print("           Reason: Forbidden. Most likely requires valid login cookies.")
    except Exception as e:
        print(f"  [ERROR] GPX download error: {e}")
    return False

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    load_cookies()

    print(f"Fetching test URL: {TEST_URL}")
    try:
        resp = session.get(TEST_URL, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        return

    json_str = extract_json_from_html(html)
    if not json_str:
        print("Failed to extract JSON from HTML.")
        return

    tours = parse_tours_from_json(json_str)
    if not tours:
        print("No tours found in JSON.")
        return

    print(f"Found {len(tours)} tours. Testing first 2...")

    for i, tour in enumerate(tours[:2]):
        tour_id = tour['id']
        name = tour['name']
        print(f"\n[{i+1}/2] Testing Tour {tour_id}: {name}")
        
        tour_dir = os.path.join(OUTPUT_DIR, str(tour_id))
        os.makedirs(tour_dir, exist_ok=True)
        
        # Save Metadata
        with open(os.path.join(tour_dir, "meta.json"), 'w', encoding='utf-8') as f:
            json.dump(tour, f, ensure_ascii=False, indent=2)
        print(f"  [OK] Metadata saved.")

        # Download GPX
        gpx_path = os.path.join(tour_dir, "course.gpx")
        download_gpx_test(tour_id, gpx_path)
        
        if i < 1:
            print("  Waiting 2s for next item...")
            time.sleep(2)

    print(f"\nTest complete. Check results in '{OUTPUT_DIR}' directory.")

if __name__ == "__main__":
    main()
