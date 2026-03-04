#!/usr/bin/env python3
"""
Korea Randonneurs (KORA) Course Crawler
- Crawls Permanents and Super Randonnée course lists
- Extracts metadata, descriptions, and external GPX/Map links (Google Drive, RWGPS)
- Saves to 'kora_courses/' directory
"""

import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Configuration
BASE_URL = "http://www.korearandonneurs.kr:8080"
URLS = {
    "permanents": "http://www.korearandonneurs.kr:8080/jsp/randonneurs/permanents",
    "superrando": "http://www.korearandonneurs.kr:8080/jsp/randonneurs/superrando"
}
OUTPUT_DIR = "kora_courses"
DELAY = 1.0  # Seconds between requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def sanitize_filename(name):
    """Sanitize string for filesystem usage"""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]


def get_soup(url):
    """Fetch URL and return BeautifulSoup object"""
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        # Force encoding if needed, but usually requests detects it well. 
        # KORA site seems to specify utf-8 in meta tag.
        resp.encoding = resp.apparent_encoding 
        return BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None


def parse_course_list(url, course_type):
    """Parse the table of courses from the list page"""
    print(f"Scanning {course_type} list at {url}...")
    soup = get_soup(url)
    if not soup:
        return []

    courses = []
    # Find the main table. Usually it's the one with class 'table' inside a 'table-responsive' div
    # Based on previous HTML dump: <table class="table">
    tables = soup.find_all('table', class_='table')
    
    target_table = None
    for t in tables:
        # Check if headers match expected columns roughly
        headers = [th.get_text(strip=True) for th in t.find_all('th')]
        if "Code" in headers or "이름" in headers:
            target_table = t
            break
    
    if not target_table:
        print(f"[WARNING] Could not find course table for {course_type}")
        return []

    # Iterate rows
    rows = target_table.find_all('tr')[1:] # Skip header
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 2:
            continue

        # Extract basic info
        # Columns: Code, Name, Distance, Elevation, TimeLimit, Start, End, Designer
        # Note: Columns might vary slightly between Perm and SuperRando, so be careful.
        # But looking at previous `curl` output, it seems consistent.
        
        try:
            code_col = cols[0]
            name_col = cols[1]
            
            code = code_col.get_text(strip=True)
            name = name_col.get_text(strip=True)
            
            # Get detail link
            link_tag = code_col.find('a') or name_col.find('a')
            detail_url = urljoin(url, link_tag['href']) if link_tag else None

            dist = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            elev = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            time_limit = cols[4].get_text(strip=True) if len(cols) > 4 else ""
            start_point = cols[5].get_text(strip=True) if len(cols) > 5 else ""
            end_point = cols[6].get_text(strip=True) if len(cols) > 6 else ""
            designer = cols[7].get_text(strip=True) if len(cols) > 7 else ""

            courses.append({
                "type": course_type,
                "code": code,
                "name": name,
                "distance": dist,
                "elevation": elev,
                "time_limit": time_limit,
                "start": start_point,
                "end": end_point,
                "designer": designer,
                "detail_url": detail_url
            })
        except Exception as e:
            print(f"[ERROR] Failed to parse row: {e}")
            continue
            
    print(f"Found {len(courses)} courses in {course_type}.")
    return courses


def extract_detail_info(url):
    """Visit detail page and extract description and links"""
    soup = get_soup(url)
    if not soup:
        return {"description": "", "links": []}

    # Description
    # Usually in <div class="product-description"> or tab content
    # Based on HTML dump: <div id="tabs-1"> ... <div class="tab-pane active" id="tab1">
    
    description = ""
    desc_div = soup.find('div', id='tab1')
    if not desc_div:
         # Fallback to product-description if tab not found
        desc_div = soup.find('div', class_='product-description')
    
    if desc_div:
        # Clean up text
        description = desc_div.get_text(separator="\n", strip=True)

    # Links (Google Drive, RWGPS, etc.)
    links = []
    # Look for all links in the main content area (product-page)
    content_area = soup.find('section', id='product-page') or soup.find('body')
    
    seen_links = set()
    if content_area:
        for a in content_area.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # Filter interesting links
            if any(x in href.lower() for x in ['drive.google.com', 'ridewithgps.com', 'maps.google.com', 'kko.to', '.gpx', '.tcx']):
                full_url = urljoin(url, href)
                if full_url not in seen_links:
                    links.append({
                        "text": text,
                        "url": full_url
                    })
                    seen_links.add(full_url)
    
    return {
        "description": description,
        "links": links
    }


def save_course_data(course):
    """Save course data to file system"""
    dirname = sanitize_filename(f"{course['code']}_{course['name']}")
    dirpath = os.path.join(OUTPUT_DIR, dirname)
    os.makedirs(dirpath, exist_ok=True)

    # Save Metadata
    with open(os.path.join(dirpath, "metadata.json"), 'w', encoding='utf-8') as f:
        json.dump(course, f, ensure_ascii=False, indent=2)

    # Save Description
    if course.get('description'):
        with open(os.path.join(dirpath, "description.txt"), 'w', encoding='utf-8') as f:
            f.write(f"Course: {course['name']} ({course['code']})\n")
            f.write(f"Distance: {course['distance']}, Elev: {course['elevation']}\n")
            f.write(f"URL: {course['detail_url']}\n")
            f.write("-" * 40 + "\n\n")
            f.write(course['description'])

    # Save Links
    if course.get('links'):
        with open(os.path.join(dirpath, "links.txt"), 'w', encoding='utf-8') as f:
            for link in course['links']:
                f.write(f"[{link['text']}] {link['url']}\n")


def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

    all_courses = []

    # 1. Collect all course metadata
    for c_type, url in URLS.items():
        courses = parse_course_list(url, c_type)
        all_courses.extend(courses)
        time.sleep(DELAY)

    print(f"\nTotal courses found: {len(all_courses)}")
    print("Starting detailed crawl...\n")

    # 2. Visit each course detail page
    for i, course in enumerate(all_courses, 1):
        print(f"[{i}/{len(all_courses)}] Processing {course['code']} {course['name']}...")
        
        if course['detail_url']:
            details = extract_detail_info(course['detail_url'])
            course.update(details)
        else:
            print("  No detail URL found.")
            course['description'] = "No detail page available."
            course['links'] = []

        # 3. Save data
        save_course_data(course)
        
        time.sleep(DELAY)

    # 4. Save global metadata index
    with open(os.path.join(OUTPUT_DIR, "all_courses.json"), 'w', encoding='utf-8') as f:
        json.dump(all_courses, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Data saved to '{OUTPUT_DIR}' directory.")


if __name__ == "__main__":
    main()
