#!/usr/bin/env python3
"""
Step 3: Detail Page Data Extractor + GPX Downloader (Final Goal)
1. Clicks card to get `smarttour` URL.
2. Opens that URL in a new tab.
3. IN THE NEW TAB:
   - Extracts Title, Metadata (Distance, Elevation, Duration), Description.
   - Extracts all Images associated with the tour.
   - Clicks "GPX 다운로드" on the page to open the download modal.
   - Clicks "Download" inside the modal to actually save the file.
   - Saves JSON metadata to a specific folder.
4. Closes tab, closes overlay, moves to next card.
"""

import os
import re
import time
import json
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

OUTPUT_DIR = "crawl_data/KOMOOT_FINAL_TEST"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    prefs = {
        "download.default_directory": os.path.abspath(OUTPUT_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_cards(driver):
    return driver.find_elements(By.CSS_SELECTOR, "div.css-dq6gmh")

def try_next_page(driver):
    print("  [Pagination] Looking for 'Next Page' button...")
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, "button.css-btlqyj")
        if not btns: return False
        
        next_btn = btns[-1]
        if next_btn.is_displayed() and next_btn.is_enabled():
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(1)
            ActionChains(driver).move_to_element(next_btn).click().perform()
            time.sleep(4) 
            return True
    except:
        pass
    return False

def _clean_image_url(src, width=1920):
    """Convert templated image URL to a usable URL."""
    if not src:
        return None
    # Replace {width}/{height}/{crop} placeholders
    src = src.replace("{width}", str(width)).replace("{height}", "").replace("{crop}", "false")
    # Remove empty query params
    src = re.sub(r'&height=(?=&|$)', '', src)
    return src


def _extract_from_embedded_json(page_source):
    """
    Extract all tour data from the kmtBoot.setProps() JSON embedded in the page.
    This contains ALL data: waypoints, highlights, tips, images, surfaces, way types, etc.
    """
    match = re.search(r'kmtBoot\.setProps\("(.+?)"\);', page_source, re.DOTALL)
    if not match:
        return None

    escaped = match.group(1)
    # Use json.loads to properly unescape the JS string (handles \" etc. without breaking Korean)
    unescaped = json.loads('"' + escaped + '"')
    return json.loads(unescaped)


def extract_data_from_detail_page(driver, real_url):
    """
    Called while the driver is focused on the NEW TAB (the smarttour URL).
    Extracts comprehensive tour data from the embedded JSON (kmtBoot.setProps).
    """
    time.sleep(3) # Wait for detail page to render completely

    # Extract Tour ID from URL
    tour_id = real_url.split("smarttour/")[1].split("?")[0] if "smarttour/" in real_url else "unknown_id"

    page_source = driver.page_source

    # Try to extract from embedded JSON first (most complete data source)
    props = _extract_from_embedded_json(page_source)

    if props:
        data = _extract_from_props(props, tour_id, real_url)
    else:
        print("      [WARN] kmtBoot.setProps not found, falling back to HTML scraping")
        data = _extract_from_html(page_source, tour_id, real_url)

    total_images = len(data.get("images", []))
    wp_count = len(data.get("waypoints", []))
    print(f"      -> Extracted: {data['title']} / {data['stats']} / {wp_count} waypoints / {total_images} images")

    # Save to disk
    tour_dir = os.path.join(OUTPUT_DIR, tour_id)
    os.makedirs(tour_dir, exist_ok=True)
    with open(os.path.join(tour_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _extract_from_props(props, tour_id, real_url):
    """Extract comprehensive data from the kmtBoot.setProps JSON."""
    dt = props.get("discoverTour", {})
    tour = props.get("page", {}).get("_embedded", {}).get("tour", {})
    tour_emb = tour.get("_embedded", {})
    gallery = props.get("gallery", {})

    data = {
        "tour_id": tour_id,
        "url": real_url,
        "title": dt.get("name", tour.get("name", "")),
        "sport": dt.get("sport", tour.get("sport", "")),
        "stats": {
            "distance": dt.get("distance"),           # meters (float)
            "duration": dt.get("duration"),            # seconds (int)
            "elevation_up": dt.get("elevationUp"),     # meters (float)
            "elevation_down": dt.get("elevationDown"), # meters (float)
        },
        "difficulty": dt.get("difficulty", {}),
        "start_point": dt.get("startPoint", {}),
        "roundtrip": dt.get("roundtrip", tour.get("roundtrip", False)),
        "description": "",
        "summary": dt.get("summary", {}),  # surfaces & wayTypes percentages
        "waypoints": [],
        "way_types": [],
        "surfaces": [],
        "images": [],       # cover/gallery images
        "gallery": [],      # user-contributed photos
    }

    # --- Description ---
    # tour_information can be a list of text blocks or empty
    tour_info = tour.get("tour_information", [])
    if isinstance(tour_info, list) and tour_info:
        data["description"] = "\n".join(
            item.get("text", "") for item in tour_info if isinstance(item, dict) and item.get("text")
        )

    # --- Cover Images ---
    cover_images = dt.get("coverImages", [])
    for ci in (cover_images if isinstance(cover_images, list) else []):
        src = ci.get("src", "")
        if src:
            data["images"].append({
                "id": ci.get("id"),
                "src": _clean_image_url(src),
                "type": "cover",
            })

    # --- Gallery (user photos) ---
    gallery_items = gallery.get("items", [])
    for gi in (gallery_items if isinstance(gallery_items, list) else []):
        src = gi.get("src", "")
        if src:
            data["gallery"].append({
                "id": gi.get("id"),
                "src": _clean_image_url(src),
                "location": gi.get("location"),
                "creator": gi.get("creator", {}).get("display_name", "") if isinstance(gi.get("creator"), dict) else "",
            })

    # --- Waypoints & Highlights (from page._embedded.tour._embedded.way_points) ---
    wp_container = tour_emb.get("way_points", {})
    wp_items = wp_container.get("_embedded", {}).get("items", [])
    if not isinstance(wp_items, list):
        wp_items = []

    for wp in wp_items:
        ref = wp.get("_embedded", {}).get("reference", {})
        wp_data = {
            "type": wp.get("type", ""),             # "poi" or "highlight"
            "index": wp.get("index"),                # position along route
            "name": ref.get("name", ""),
            "category": ref.get("category", ""),
            "location": ref.get("location", {}),
            "text": ref.get("text", ""),             # POI description
            "tips": [],
            "images": [],
        }

        ref_emb = ref.get("_embedded", {})

        # Tips (user recommendations)
        tips_container = ref_emb.get("tips", {})
        if isinstance(tips_container, dict):
            tip_items = tips_container.get("_embedded", {}).get("items", [])
            for tip in (tip_items if isinstance(tip_items, list) else []):
                creator = tip.get("_embedded", {}).get("creator", {})
                wp_data["tips"].append({
                    "text": tip.get("text", ""),
                    "author": creator.get("display_name", ""),
                })

        # Images on this waypoint
        imgs_container = ref_emb.get("images", {})
        if isinstance(imgs_container, dict):
            img_items = imgs_container.get("_embedded", {}).get("items", [])
            for img in (img_items if isinstance(img_items, list) else []):
                src = img.get("src", "")
                if src:
                    wp_data["images"].append({
                        "id": img.get("id"),
                        "src": _clean_image_url(src),
                    })

        data["waypoints"].append(wp_data)

    # --- Way Types (segment-level detail) ---
    wt_data = tour_emb.get("way_types", {})
    wt_items = wt_data.get("items", [])
    if isinstance(wt_items, list):
        data["way_types"] = wt_items  # [{from, to, element}, ...]

    # --- Surfaces (segment-level detail) ---
    sf_data = tour_emb.get("surfaces", {})
    sf_items = sf_data.get("items", [])
    if isinstance(sf_items, list):
        data["surfaces"] = sf_items  # [{from, to, element}, ...]

    return data


def _extract_from_html(page_source, tour_id, real_url):
    """Fallback: scrape from rendered HTML if embedded JSON not available."""
    soup = BeautifulSoup(page_source, "html.parser")

    data = {
        "tour_id": tour_id,
        "url": real_url,
        "title": "",
        "stats": {},
        "description": "",
        "images": [],
        "waypoints": [],
    }

    title_tag = soup.find("h1")
    if title_tag:
        data["title"] = title_tag.text.strip()

    stats_divs = soup.find_all("div", attrs={"data-test-id": re.compile(r"t_distance|t_duration|t_elevation")})
    for stat in stats_divs:
        key = stat.get("data-test-id")
        val = stat.find(attrs={"data-test-id": re.compile(r".*_value$")})
        if not val:
            val = stat.find("p")
        if val:
            data["stats"][key] = val.text.strip()

    desc_tag = soup.find("div", attrs={"data-test-id": "tour-description"})
    if desc_tag:
        data["description"] = desc_tag.text.strip()

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "cloudfront" in src or "maps.komoot" in src:
            clean_src = src.split("?")[0]
            if clean_src not in data["images"]:
                data["images"].append(clean_src)

    return data
        
    # 6. DOWNLOAD GPX via TWO-STEP MODAL
    try:
        # Step 6-1: Click the initial "GPX 다운로드" button on the detail page
        print("      -> Looking for initial GPX Download button...")
        dl_xpath = "//a[@aria-label='GPX 다운로드'] | //a[@aria-label='Download GPX']"
        initial_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, dl_xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", initial_btn)
        time.sleep(0.5)
        ActionChains(driver).move_to_element(initial_btn).click().perform()
        print("      -> Clicked initial GPX button. Waiting for modal...")
        
        # Step 6-2: Wait for the modal and click the final "Download" button inside it
        # Exact element provided by user: <a role="button" class="css-1tg45r7" aria-label="Download"><p class="css-toyscm">Download</p></a>
        time.sleep(2) # Give modal time to animate in
        
        modal_dl_xpath = "//a[@aria-label='Download' or @aria-label='다운로드']"
        final_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, modal_dl_xpath)))
        ActionChains(driver).move_to_element(final_btn).click().perform()
        
        print("      [SUCCESS] Clicked Final Download button inside Modal.")
        time.sleep(5) # Wait for file to fully download before closing tab
        
    except Exception as e:
        print(f"      [ERROR] Failed during the GPX Modal Download process: {e}")

def process_card(driver, card_element, index, page_num):
    print(f"\n[Page {page_num} - Card {index}] Processing...")
    
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_element)
    time.sleep(1)
    
    # 1. Click card to open overlay
    try:
        ActionChains(driver).move_to_element(card_element).click().perform()
        time.sleep(3)
    except Exception as e:
        print(f"  [ERROR] Failed to click card: {e}")
        return False

    # 2. Extract the true ID/URL from the overlay
    real_url = None
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href")
            if href and ("/smarttour/" in href or "/tour/" in href):
                real_url = href
                break
    except:
        pass

    # 3. Open URL in new tab & Extract Data
    original_window = driver.current_window_handle
    if real_url:
        try:
            print(f"  -> Opening Detail Page: {real_url}")
            driver.execute_script(f"window.open('{real_url}', '_blank');")
            time.sleep(2)
            
            # Switch to the new tab
            driver.switch_to.window(driver.window_handles[-1])
            
            # ** DO ALL THE HEAVY LIFTING HERE **
            extract_data_from_detail_page(driver, real_url)
            
            # Close tab and return
            driver.close()
            driver.switch_to.window(original_window)
            print("  -> Detail Page processed and closed.")
        except Exception as e:
            print(f"  [ERROR] Failed during detail page extraction: {e}")
            driver.switch_to.window(original_window) 
    else:
        print("  [ERROR] No valid URL found in overlay.")

    # 4. Close the Overlay
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(2)
    except:
        pass
        
    return True

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    driver = setup_driver()
    
    try:
        print("\n=== PHASE 1: LOGIN & SETUP ===")
        print("1. Login manually.")
        print("2. Navigate to Discover and setup your view.")
        print("3. Scroll down so the list loads.")
        print("4. Press ENTER when the list is completely ready.")
        driver.get("https://www.komoot.com/login")
        input()
        
        print("\n=== PHASE 2: AUTOMATION START (DETAIL PAGE TEST) ===")
        time.sleep(2) 
        
        cards = get_cards(driver)
        if cards:
            # ONLY Process the FIRST card to see if data extraction & download works perfectly
            process_card(driver, cards[0], index=1, page_num=1)
            
        print("\n=== TEST COMPLETE ===")
        print(f"Check '{OUTPUT_DIR}' for downloaded GPX and metadata.json")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        time.sleep(2)
        driver.quit()

if __name__ == "__main__":
    main()
