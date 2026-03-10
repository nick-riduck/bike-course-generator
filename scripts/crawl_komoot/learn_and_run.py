#!/usr/bin/env python3
"""
Komoot Interactive Crawler: Learn & Automate
1. Login & Setup Phase.
2. Learning Phase: User clicks ONE tour -> Script learns the URL pattern.
3. Execution Phase: Script iterates through matching links to scrape & download.
"""

import os
import time
import json
import random
import re
import requests
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
OUTPUT_DIR = "crawl_data/KOMOOT_AUTO"
TOTAL_TARGET = 880

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def download_gpx(driver, tour_id, output_dir):
    """Download GPX using current session cookies"""
    download_url = f"https://www.komoot.com/api/v007/tours/{tour_id}/download?format=gpx"
    try:
        cookies = driver.get_cookies()
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
        headers = {"User-Agent": driver.execute_script("return navigator.userAgent;")}
        
        resp = session.get(download_url, headers=headers)
        if resp.status_code == 200:
            with open(os.path.join(output_dir, "course.gpx"), 'wb') as f:
                f.write(resp.content)
            return True
        else:
            print(f"    [GPX] Failed status: {resp.status_code}")
    except Exception as e:
        print(f"    [GPX] Error: {e}")
    return False

def save_metadata(driver, tour_id, tour_url, output_dir):
    """Extract and save metadata"""
    try:
        title = driver.title.replace(" | Komoot", "").strip()
        description = ""
        try:
            desc_meta = driver.find_element(By.CSS_SELECTOR, 'meta[name="description"]')
            description = desc_meta.get_attribute("content")
        except: pass

        data = {
            "id": tour_id,
            "url": tour_url,
            "title": title,
            "description": description,
            "crawled_at": time.time()
        }
        with open(os.path.join(output_dir, "meta.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

def extract_links_by_pattern(driver, pattern_regex):
    """Finds all links matching the learned regex pattern"""
    links = set()
    try:
        elements = driver.find_elements(By.TAG_NAME, 'a')
        for e in elements:
            href = e.get_attribute('href')
            if href and re.search(pattern_regex, href):
                links.add(href)
    except: pass
    return list(links)

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    driver = setup_driver()
    processed_urls = set()
    
    try:
        # Phase 1: Login
        print("\n" + "="*60)
        print("PHASE 1: LOGIN")
        print("1. Browser opening...")
        print("2. Login manually.")
        print("3. Press ENTER here when logged in.")
        print("="*60)
        
        driver.get("https://www.komoot.com/login")
        input()

        # Phase 2: Setup View
        print("\n" + "="*60)
        print("PHASE 2: SETUP VIEW")
        print("1. Navigate to Discover page.")
        print("2. Adjust map/filters to show the list.")
        print("3. Press ENTER here when the list is ready.")
        print("="*60)
        input()

        # Phase 3: Learn Pattern
        print("\n" + "="*60)
        print("PHASE 3: TEACH ME")
        print("1. Click on ANY ONE tour in the list.")
        print("2. Wait for the tour details page to load.")
        print("3. Press ENTER here.")
        print("="*60)
        input()
        
        sample_url = driver.current_url
        print(f"Learned URL: {sample_url}")
        
        # Derive pattern from sample URL
        # e.g., https://www.komoot.com/tour/123456 -> regex: /tour/\d+
        if '/tour/' in sample_url:
            url_pattern = r"/tour/\d+"
        elif '/smarttour/' in sample_url:
            url_pattern = r"/smarttour/\d+"
        elif '/highlight/' in sample_url:
            url_pattern = r"/highlight/\d+"
        else:
            # Fallback: digits at end
            url_pattern = r"/\d+"
            
        print(f"Derived Pattern Regex: {url_pattern}")
        
        print("Going back to list...")
        driver.back()
        time.sleep(3)

        # Phase 4: Automation
        print("\n" + "="*60)
        print("PHASE 4: AUTOMATION START")
        print(f"Target: {TOTAL_TARGET} items.")
        print("="*60)

        count = 0
        while count < TOTAL_TARGET:
            # Detect
            current_links = extract_links_by_pattern(driver, url_pattern)
            new_links = [l for l in current_links if l not in processed_urls]
            
            print(f"\n[Scan] Found {len(current_links)} total, {len(new_links)} new.")
            
            if not new_links:
                print("  -> No new links. Scrolling...")
                driver.execute_script("window.scrollBy(0, 1000);")
                time.sleep(3)
                
                # Retry
                current_links = extract_links_by_pattern(driver, url_pattern)
                new_links = [l for l in current_links if l not in processed_urls]
                
                if not new_links:
                    print("  -> Still empty. (p)ause, (q)uit, (Enter) retry?")
                    choice = input("Option: ").strip().lower()
                    if choice == 'q': break
                    if choice == 'p': input("Paused. Press ENTER to resume.")
                    continue

            # Process
            for url in new_links:
                if count >= TOTAL_TARGET: break
                
                print(f"[{count+1}/{TOTAL_TARGET}] Processing: {url}")
                
                driver.execute_script(f"window.open('{url}', '_blank');")
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(random.uniform(2.5, 4.0))
                
                try:
                    # Parse ID
                    # Try finding digits after the known pattern keyword
                    if '/tour/' in url:
                        tour_id = url.split('/tour/')[1].split('/')[0].split('?')[0]
                    elif '/smarttour/' in url:
                        tour_id = url.split('/smarttour/')[1].split('/')[0].split('?')[0]
                    else:
                        tour_id = [x for x in url.split('/') if x.isdigit()][-1]
                    
                    tour_dir = os.path.join(OUTPUT_DIR, tour_id)
                    os.makedirs(tour_dir, exist_ok=True)
                    
                    save_metadata(driver, tour_id, url, tour_dir)
                    if download_gpx(driver, tour_id, tour_dir):
                        print("    -> GPX Downloaded.")
                    else:
                        print("    -> GPX Failed.")
                        
                except Exception as e:
                    print(f"    Error: {e}")

                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                
                processed_urls.add(url)
                count += 1
                time.sleep(random.uniform(1.0, 2.0))
            
            print("  -> Batch done. Scrolling...")
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(3)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"\nCritical Error: {e}")
    finally:
        driver.quit()
        print("Driver closed.")

if __name__ == "__main__":
    main()
