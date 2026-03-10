#!/usr/bin/env python3
"""
Komoot Course Crawler (Selenium Based)

- Uses Selenium to automate browsing, scrolling, and clicking.
- Extracts metadata and downloads GPX files.
- Designed to run slowly (10 hours target) to mimic human behavior and avoid bans.
"""

import os
import time
import json
import random
import argparse
import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
START_URL = "https://www.komoot.com/discover/Current_location/@37.5049040,127.0640070/tours?sport=touringbicycle&map=true&max_distance=500&pageNumber=1"
OUTPUT_DIR = "crawl_data/KOMOOT_SELENIUM"
TOTAL_ITEMS_ESTIMATE = 880
TOTAL_DURATION_HOURS = 10
DELAY_BASE = (TOTAL_DURATION_HOURS * 3600) / TOTAL_ITEMS_ESTIMATE  # ~41 seconds

# --- Helper Functions ---

def setup_driver(headless=False):
    """Setup Chrome Driver"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # Mimic a real user agent
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def random_sleep(base_seconds=2.0, variance=0.5):
    """Sleep for a random duration around base_seconds"""
    duration = random.uniform(base_seconds * (1 - variance), base_seconds * (1 + variance))
    time.sleep(duration)

def wait_for_login(driver):
    """Pause script to allow manual login"""
    print("\n" + "="*50)
    print("PLEASE LOGIN MANUALLY IN THE BROWSER WINDOW NOW.")
    print("Navigate to https://www.komoot.com/login if not already there.")
    print("After logging in, press ENTER here to continue crawling...")
    print("="*50 + "\n")
    input()
    print("Resuming crawl...")

def scroll_to_bottom(driver):
    """Scroll to the bottom of the page to load more content"""
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    random_sleep(2.0)

def extract_tour_urls(driver):
    """Find all tour links on the current page"""
    # Komoot tour links usually look like /tour/123456789 or /smarttour/12345
    
    links = set()
    elements = driver.find_elements(By.TAG_NAME, 'a')
    
    print(f"  [Debug] Found {len(elements)} anchor tags.")
    
    for a in elements:
        try:
            href = a.get_attribute('href')
            if not href:
                continue
                
            # print(f"  [Debug] Link: {href}") # Uncomment to see all links if needed
            
            # Check for tour patterns
            if '/tour/' in href or '/smarttour/' in href:
                # Basic validation: check for digits
                parts = href.split('/')
                # Filter out non-content links like /tour/create
                if any(part.isdigit() for part in parts):
                    full_url = href if href.startswith('http') else "https://www.komoot.com" + href
                    links.add(full_url)
        except Exception as e:
            # Stale element reference is common during scrolling
            pass
                 
    return list(links)

def process_tour_page(driver, tour_url):
    """Visit a tour page, extract metadata, and download GPX"""
    print(f"Visiting: {tour_url}")
    driver.get(tour_url)
    random_sleep(3.0) # Wait for page load

    # 1. Extract Metadata
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Title
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Tour"
        
        # ID from URL
        tour_id = tour_url.split('/')[-1].split('?')[0] # simplistic
        if not tour_id.isdigit():
             # Try previous segment if URL ends with query params or slash
             tour_id = tour_url.split('/')[-2]

        # Stats (Distance, Elevation, etc.)
        # These are often in specific divs. We might need specific selectors.
        # For now, let's dump the raw text of stats container if found, or just skip detailed parsing.
        # A robust crawler would target specific classes.
        
        # Generic approach: Meta description often has summary
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc['content'] if meta_desc else ""

        tour_data = {
            "id": tour_id,
            "url": tour_url,
            "title": title,
            "description": description,
            # Add more specific fields here if selectors are known
        }
        
        # Save Metadata
        tour_dir = os.path.join(OUTPUT_DIR, tour_id)
        os.makedirs(tour_dir, exist_ok=True)
        
        with open(os.path.join(tour_dir, "meta.json"), 'w', encoding='utf-8') as f:
            json.dump(tour_data, f, ensure_ascii=False, indent=2)
            
        print(f"  [Meta] Saved for {tour_id}")

        # 2. Download GPX
        # Find "Export to GPS device" or similar button.
        # Usually it's a button that opens a modal, or a direct link /api/v007/tours/{id}/download
        
        download_url = f"https://www.komoot.com/api/v007/tours/{tour_id}/download?format=gpx"
        
        # Use requests with cookies from selenium session
        cookies = driver.get_cookies()
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
        # Mimic headers
        headers = {
            "User-Agent": driver.execute_script("return navigator.userAgent;")
        }
        
        print(f"  [GPX] Attempting download from {download_url}")
        resp = session.get(download_url, headers=headers)
        
        if resp.status_code == 200:
            gpx_path = os.path.join(tour_dir, "course.gpx")
            with open(gpx_path, 'wb') as f:
                f.write(resp.content)
            print(f"  [GPX] Success! Saved to {gpx_path}")
        else:
            print(f"  [GPX] Failed. Status: {resp.status_code}")
            
    except Exception as e:
        print(f"  [Error] Processing tour page failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Komoot Selenium Crawler")
    parser.add_argument('--headless', action='store_true', help="Run in headless mode")
    parser.add_argument('--no-login', action='store_true', help="Skip manual login pause")
    args = parser.parse_args()

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    driver = setup_driver(headless=args.headless)
    
    try:
        # 1. Login Phase
        if not args.no_login:
            driver.get("https://www.komoot.com/login")
            wait_for_login(driver)
        
        # 2. Discover / List Phase
        print(f"Navigating to start URL: {START_URL}")
        driver.get(START_URL)
        random_sleep(5.0)
        
        # Scroll a few times to load initial batch
        for _ in range(3):
            scroll_to_bottom(driver)
            
        # Extract initial list of tours
        tour_urls = extract_tour_urls(driver)
        print(f"Found {len(tour_urls)} tours initially.")
        
        # 3. Crawl Loop
        processed_count = 0
        
        # We might need to keep scrolling and extracting if we want ALL 880.
        # For the prototype, let's just process what we found or implement a generator.
        
        # To get 880 items, we likely need to paginate or keep scrolling.
        # Komoot Discover uses pagination parameters in URL usually (pageNumber=1).
        
        # Strategy: Iterate pages
        current_page = 1
        processed_urls = set()
        
        while processed_count < TOTAL_ITEMS_ESTIMATE:
            
            # Update URL for pagination if not already there
            if "pageNumber=" in driver.current_url:
                if str(current_page) not in driver.current_url:
                     # This logic assumes the URL updates or we navigate manually
                     next_page_url = START_URL.replace("pageNumber=1", f"pageNumber={current_page}")
                     if next_page_url != driver.current_url:
                         driver.get(next_page_url)
                         random_sleep(5.0)
            
            # Extract links on current page
            current_page_urls = set(extract_tour_urls(driver))
            new_urls = current_page_urls - processed_urls
            
            if not new_urls:
                print("No new tours found on this page. Stopping.")
                break
                
            print(f"Page {current_page}: Found {len(new_urls)} new tours.")
            
            for url in new_urls:
                if processed_count >= TOTAL_ITEMS_ESTIMATE:
                    break
                    
                process_tour_page(driver, url)
                processed_urls.add(url)
                processed_count += 1
                
                # Sleep to match 10-hour target
                print(f"Sleeping {DELAY_BASE:.1f}s...")
                random_sleep(DELAY_BASE)
                
                # Go back to list page if we navigated away? 
                # Actually process_tour_page navigates away. 
                # So we must go back or open in new tab.
                # Simplest: Navigate back to list page for next item? No, that's slow.
                # Better: Collect all URLs for the page first, then visit them one by one.
                # BUT process_tour_page uses `driver.get`.
                # So we are fine iterating the list `new_urls`.
                
            current_page += 1
            
            # Navigate to next page for the next iteration
            next_page_url = START_URL.replace("pageNumber=1", f"pageNumber={current_page}")
            print(f"Moving to Page {current_page}...")
            driver.get(next_page_url)
            random_sleep(5.0)

    except KeyboardInterrupt:
        print("\nStopping crawler...")
    except Exception as e:
        print(f"\nCritical Error: {e}")
    finally:
        driver.quit()
        print("Driver closed.")

if __name__ == "__main__":
    main()
