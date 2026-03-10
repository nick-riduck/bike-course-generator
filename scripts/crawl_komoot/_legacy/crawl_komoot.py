#!/usr/bin/env python3
"""
Komoot Course Crawler
- Crawls tours from a Komoot Discover URL
- Extracts metadata and attempts GPX download
- Designed to run slowly over 10 hours for ~880 items
"""

import os
import re
import time
import json
import random
import requests
import argparse
from bs4 import BeautifulSoup

# Configuration
BASE_URL_TEMPLATE = "https://www.komoot.com/discover/Current_location/@37.5049040,127.0640070/tours?sport=touringbicycle&map=true&max_distance=500&pageNumber={}"
OUTPUT_DIR = "crawl_data/KOMOOT"
TOTAL_ITEMS_ESTIMATE = 880
TOTAL_DURATION_HOURS = 10
DELAY_BASE = (TOTAL_DURATION_HOURS * 3600) / TOTAL_ITEMS_ESTIMATE  # ~41 seconds

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
}

session = requests.Session()
session.headers.update(HEADERS)

def load_cookies(cookie_file):
    """Load cookies from a Netscape format file or simple line-based format"""
    if not os.path.exists(cookie_file):
        print(f"[WARNING] Cookie file '{cookie_file}' not found. Crawling as guest (might be limited).")
        return

    print(f"Loading cookies from {cookie_file}...")
    with open(cookie_file, 'r') as f:
        for line in f:
            if not line.startswith('#') and line.strip():
                parts = line.strip().split('	')
                if len(parts) >= 7:
                    session.cookies.set(parts[5], parts[6], domain=parts[0], path=parts[2])
                elif '=' in line:
                    key, val = line.strip().split('=', 1)
                    session.cookies.set(key, val)

def get_soup(url):
    """Fetch URL and return BeautifulSoup object"""
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'html.parser'), resp.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None, None

def extract_json_from_html(html_content):
    """Extract the kmtBoot.setProps JSON data"""
    # Pattern to find kmtBoot.setProps("...");
    # We need to be careful about escaped quotes.
    # Usually it's strictly JSON string inside double quotes.
    
    # Try to find the script content
    match = re.search(r'kmtBoot\.setProps\("(.*)"\);', html_content)
    if not match:
        # Fallback: sometimes it's single quotes or different formatting
        match = re.search(r"kmtBoot\.setProps\('(.*)'\);", html_content)
    
    if match:
        json_str_escaped = match.group(1)
        try:
            # The string is JSON escaped (e.g. " for ")
            # We can use json.loads to parse the string literal into a JSON string
            # Then json.loads again to parse the JSON object.
            # But wait, python's json.loads expects a valid JSON string.
            # If it's inside JS double quotes, backslashes are escaped.
            # We can try using codecs.decode(json_str_escaped, 'unicode_escape') but that might be risky for UTF-8.
            # Better: create a dummy JSON string wrapping it and parse.
            
            # Actually, standard JSON string format.
            return json.loads(f'"{json_str_escaped}"')
        except Exception as e:
            print(f"[ERROR] Failed to unescape JSON string: {e}")
            # Try raw unescape if simple
            try:
                return json.loads(json_str_escaped.replace('"', '"').replace('', ''))
            except:
                pass
            return None
            
    return None

def parse_tours_from_json(data_json):
    """Parse tours from the extracted JSON"""
    tours = []
    
    # Navigate: page -> tours -> _embedded -> items
    # OR: page -> _embedded -> tours -> items
    # OR: props -> page...
    
    try:
        # It's usually a string that needs to be parsed again as JSON object
        data = json.loads(data_json)
        
        page_data = data.get('page', {})
        tours_data = page_data.get('tours', {})
        
        # Check _embedded directly in page or in tours
        embedded = tours_data.get('_embedded', {})
        items = embedded.get('items', [])
        
        if not items:
            # Check other locations
            embedded = page_data.get('_embedded', {})
            tours_embedded = embedded.get('tours', {})
            items = tours_embedded.get('_embedded', {}).get('items', [])
            
        if not items:
             # Try simple 'items' in tours
             items = tours_data.get('items', [])

        for item in items:
            # Extract basic info
            tour_id = item.get('id')
            name = item.get('name')
            status = item.get('status')
            distance = item.get('distance')
            elevation = item.get('elevation_up')
            duration = item.get('duration')
            
            if tour_id:
                tours.append({
                    "id": tour_id,
                    "name": name,
                    "status": status,
                    "distance": distance,
                    "elevation": elevation,
                    "duration": duration,
                    "source_data": item
                })
                
    except Exception as e:
        print(f"[ERROR] JSON parsing logic failed: {e}")
        
    return tours

def download_gpx(tour_id, output_path):
    """Attempt to download GPX for a tour"""
    # Endpoint: https://www.komoot.com/api/v007/tours/{id}/download
    # Requires login cookies usually.
    url = f"https://www.komoot.com/api/v007/tours/{tour_id}/download"
    try:
        resp = session.get(url, params={'format': 'gpx'}, timeout=30)
        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(resp.content)
            print(f"  [OK] GPX downloaded: {output_path}")
            return True
        elif resp.status_code == 403:
            print(f"  [SKIP] GPX download forbidden (needs login/cookies): {url}")
        else:
            print(f"  [SKIP] GPX download failed ({resp.status_code}): {url}")
    except Exception as e:
        print(f"  [ERROR] GPX download error: {e}")
    return False

def save_tour_data(tour):
    """Save tour metadata and GPX"""
    tour_id = str(tour['id'])
    dir_path = os.path.join(OUTPUT_DIR, tour_id)
    os.makedirs(dir_path, exist_ok=True)
    
    # Save Metadata
    meta_path = os.path.join(dir_path, "meta.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(tour, f, ensure_ascii=False, indent=2)
        
    # Save GPX
    gpx_path = os.path.join(dir_path, "course.gpx")
    if not os.path.exists(gpx_path):
        download_gpx(tour['id'], gpx_path)
    else:
        print(f"  [INFO] GPX already exists.")

def main():
    parser = argparse.ArgumentParser(description="Komoot Crawler")
    parser.add_argument('--cookies', help="Path to cookies file (Netscape or name=val)", default="komoot_cookies.txt")
    parser.add_argument('--start-page', type=int, default=1, help="Page to start crawling from")
    args = parser.parse_args()

    # Load cookies if available
    load_cookies(args.cookies)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created output directory: {OUTPUT_DIR}")

    page = args.start_page
    total_processed = 0
    
    print(f"Starting crawl. Target: ~{TOTAL_ITEMS_ESTIMATE} items over {TOTAL_DURATION_HOURS} hours.")
    print(f"Base delay per item: {DELAY_BASE:.1f} seconds (randomized).")

    while True:
        url = BASE_URL_TEMPLATE.format(page)
        print(f"\n[Page {page}] Fetching {url}...")
        
        soup, html = get_soup(url)
        if not html:
            print("Failed to get page. Retrying in 60s...")
            time.sleep(60)
            continue

        # Parse data
        json_data = extract_json_from_html(html)
        if not json_data:
            print("[WARNING] No embedded JSON data found. Komoot might have changed layout or blocked us.")
            # Depending on strictness, we might want to break or wait.
            # But let's try to see if it's just an empty page or captcha.
            if "captcha" in html.lower():
                print("[CRITICAL] CAPTCHA detected! Stopping.")
                break
            break

        tours = parse_tours_from_json(json_data)
        if not tours:
            print(f"[Page {page}] No tours found. End of list or parsing error.")
            break
            
        print(f"[Page {page}] Found {len(tours)} tours.")
        
        for tour in tours:
            total_processed += 1
            print(f"[{total_processed}/{TOTAL_ITEMS_ESTIMATE}] Processing Tour {tour.get('id')}: {tour.get('name')}...")
            
            save_tour_data(tour)
            
            # Randomized delay
            delay = random.uniform(DELAY_BASE * 0.8, DELAY_BASE * 1.2)
            print(f"  Sleeping for {delay:.1f}s...")
            time.sleep(delay)
            
            if total_processed >= TOTAL_ITEMS_ESTIMATE:
                print("Reached target item count.")
                return

        page += 1

if __name__ == "__main__":
    main()
