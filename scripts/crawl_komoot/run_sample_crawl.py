#!/usr/bin/env python3
"""
Sample Crawler - 페이지 1,2,3의 첫 번째 카드만 크롤링 (테스트용)
딜레이: 2초
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

OUTPUT_DIR = "crawl_data/KOMOOT_SAMPLE"
TEST_PAGES = 3      # 3페이지만
DELAY = 2           # 2초 대기


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    prefs = {
        "download.default_directory": os.path.abspath(OUTPUT_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def get_cards(driver):
    return driver.find_elements(By.CSS_SELECTOR, "div.css-dq6gmh")


def try_next_page(driver):
    print("  [Pagination] Looking for Next Page button...")
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, "button.css-btlqyj")
        if not btns:
            print("  [Pagination] Not found.")
            return False
        next_btn = btns[-1]
        if next_btn.is_displayed() and next_btn.is_enabled():
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(1)
            ActionChains(driver).move_to_element(next_btn).click().perform()
            print("  [Pagination] Clicked. Waiting...")
            time.sleep(5)
            return True
    except Exception as e:
        print(f"  [Pagination] Error: {e}")
    return False


# === Image URL Helper ===

def _clean_image_url(src, width=1920):
    if not src:
        return None
    src = src.replace("{width}", str(width)).replace("{height}", "").replace("{crop}", "false")
    src = re.sub(r'&height=(?=&|$)', '', src)
    return src


# === Data Extraction ===

def _extract_from_embedded_json(page_source):
    match = re.search(r'kmtBoot\.setProps\("(.+?)"\);', page_source, re.DOTALL)
    if not match:
        return None
    escaped = match.group(1)
    unescaped = json.loads('"' + escaped + '"')
    return json.loads(unescaped)


def _extract_from_props(props, tour_id, real_url):
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
            "distance": dt.get("distance"),
            "duration": dt.get("duration"),
            "elevation_up": dt.get("elevationUp"),
            "elevation_down": dt.get("elevationDown"),
        },
        "difficulty": dt.get("difficulty", {}),
        "start_point": dt.get("startPoint", {}),
        "roundtrip": dt.get("roundtrip", tour.get("roundtrip", False)),
        "description": "",
        "summary": dt.get("summary", {}),
        "waypoints": [],
        "way_types": [],
        "surfaces": [],
        "images": [],
        "gallery": [],
    }

    # Description
    tour_info = tour.get("tour_information", [])
    if isinstance(tour_info, list) and tour_info:
        data["description"] = "\n".join(
            item.get("text", "") for item in tour_info if isinstance(item, dict) and item.get("text")
        )

    # Cover Images
    for ci in (dt.get("coverImages") or []):
        src = ci.get("src", "")
        if src:
            data["images"].append({"id": ci.get("id"), "src": _clean_image_url(src), "type": "cover"})

    # Gallery
    for gi in (gallery.get("items") or []):
        src = gi.get("src", "")
        if src:
            creator = gi.get("creator")
            data["gallery"].append({
                "id": gi.get("id"),
                "src": _clean_image_url(src),
                "location": gi.get("location"),
                "creator": creator.get("display_name", "") if isinstance(creator, dict) else "",
            })

    # Waypoints & Highlights
    wp_items = (tour_emb.get("way_points") or {}).get("_embedded", {}).get("items") or []
    for wp in wp_items:
        ref = wp.get("_embedded", {}).get("reference", {})
        wp_data = {
            "type": wp.get("type", ""),
            "index": wp.get("index"),
            "name": ref.get("name", ""),
            "category": ref.get("category", ""),
            "location": ref.get("location", {}),
            "text": ref.get("text", ""),
            "tips": [],
            "images": [],
        }
        ref_emb = ref.get("_embedded", {})

        tips_container = ref_emb.get("tips", {})
        if isinstance(tips_container, dict):
            for tip in (tips_container.get("_embedded", {}).get("items") or []):
                creator = tip.get("_embedded", {}).get("creator", {})
                wp_data["tips"].append({
                    "text": tip.get("text", ""),
                    "author": creator.get("display_name", ""),
                })

        imgs_container = ref_emb.get("images", {})
        if isinstance(imgs_container, dict):
            for img in (imgs_container.get("_embedded", {}).get("items") or []):
                src = img.get("src", "")
                if src:
                    wp_data["images"].append({"id": img.get("id"), "src": _clean_image_url(src)})

        data["waypoints"].append(wp_data)

    data["way_types"] = (tour_emb.get("way_types") or {}).get("items") or []
    data["surfaces"] = (tour_emb.get("surfaces") or {}).get("items") or []

    return data


def _extract_from_html(page_source, tour_id, real_url):
    soup = BeautifulSoup(page_source, "html.parser")
    data = {"tour_id": tour_id, "url": real_url, "title": "", "stats": {},
            "description": "", "images": [], "waypoints": []}
    title_tag = soup.find("h1")
    if title_tag:
        data["title"] = title_tag.text.strip()
    for stat in soup.find_all("div", attrs={"data-test-id": re.compile(r"t_distance|t_duration|t_elevation")}):
        key = stat.get("data-test-id")
        val = stat.find(attrs={"data-test-id": re.compile(r".*_value$")}) or stat.find("p")
        if val:
            data["stats"][key] = val.text.strip()
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "cloudfront" in src or "maps.komoot" in src:
            clean_src = src.split("?")[0]
            if clean_src not in data["images"]:
                data["images"].append(clean_src)
    return data


# === Detail Page ===

def extract_data_from_detail_page(driver, real_url):
    time.sleep(3)
    tour_id = real_url.split("smarttour/")[1].split("?")[0] if "smarttour/" in real_url else \
              real_url.split("tour/")[1].split("?")[0] if "tour/" in real_url else "unknown_id"

    props = _extract_from_embedded_json(driver.page_source)
    if props:
        data = _extract_from_props(props, tour_id, real_url)
    else:
        print("      [WARN] JSON not found, falling back to HTML")
        data = _extract_from_html(driver.page_source, tour_id, real_url)

    wp_count = len(data.get("waypoints", []))
    img_count = len(data.get("images", []))
    print(f"      -> {data['title']} | {wp_count} waypoints | {img_count} images")

    tour_dir = os.path.join(OUTPUT_DIR, tour_id)
    os.makedirs(tour_dir, exist_ok=True)
    with open(os.path.join(tour_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # GPX download
    try:
        print("      -> GPX Download...")
        dl_xpath = "//a[@aria-label='GPX 다운로드'] | //a[@aria-label='Download GPX']"
        initial_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, dl_xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", initial_btn)
        time.sleep(0.5)
        ActionChains(driver).move_to_element(initial_btn).click().perform()
        time.sleep(2)
        modal_dl_xpath = "//a[@aria-label='Download' or @aria-label='다운로드']"
        final_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, modal_dl_xpath)))
        ActionChains(driver).move_to_element(final_btn).click().perform()
        print("      -> [OK] GPX downloaded.")
        time.sleep(3)
    except Exception as e:
        print(f"      -> [ERROR] GPX failed: {e}")

    return tour_id


def process_first_card(driver, page_num):
    """현재 페이지의 첫 번째 카드만 처리."""
    cards = get_cards(driver)
    if not cards:
        print(f"  [Page {page_num}] No cards found!")
        return None

    card = cards[0]
    print(f"\n[Page {page_num} - Card 1] Processing...")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
    time.sleep(1)

    # Click card → overlay
    try:
        ActionChains(driver).move_to_element(card).click().perform()
        time.sleep(3)
    except Exception as e:
        print(f"  [ERROR] Click failed: {e}")
        return None

    # Extract URL from overlay
    real_url = None
    try:
        for link in driver.find_elements(By.TAG_NAME, "a"):
            href = link.get_attribute("href")
            if href and ("/smarttour/" in href or "/tour/" in href):
                real_url = href
                break
    except:
        pass

    tour_id = None
    if real_url:
        original_window = driver.current_window_handle
        try:
            print(f"  -> Opening: {real_url}")
            driver.execute_script(f"window.open('{real_url}', '_blank');")
            time.sleep(DELAY)
            driver.switch_to.window(driver.window_handles[-1])

            tour_id = extract_data_from_detail_page(driver, real_url)

            driver.close()
            driver.switch_to.window(original_window)
            print("  -> Done, tab closed.")
        except Exception as e:
            print(f"  -> [ERROR] {e}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                driver.switch_to.window(original_window)
            except:
                pass
    else:
        print("  [ERROR] No URL found in overlay.")

    # Close overlay
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(DELAY)
    except:
        pass

    return tour_id


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    driver = setup_driver()

    try:
        print("\n=== SAMPLE CRAWL (3 pages × 1st card only) ===")
        print(f"Output: {OUTPUT_DIR}/")
        print("\n1. Login manually")
        print("2. Navigate to Discover, set filters")
        print("3. Scroll so the list loads")
        print("4. Press ENTER\n")
        driver.get("https://www.komoot.com/login")
        input(">>> ENTER to start...")

        results = []
        for page in range(1, TEST_PAGES + 1):
            tour_id = process_first_card(driver, page)
            if tour_id:
                results.append(tour_id)
                print(f"  ✓ Page {page} done: {tour_id}")

            if page < TEST_PAGES:
                time.sleep(DELAY)
                if not try_next_page(driver):
                    print("  Next page button not found. Waiting...")
                    input(">>> Navigate manually, then ENTER...")

        print(f"\n=== SAMPLE COMPLETE: {len(results)}/{TEST_PAGES} ===")
        for tid in results:
            print(f"  - {OUTPUT_DIR}/{tid}/metadata.json")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        time.sleep(1)
        driver.quit()


if __name__ == "__main__":
    main()
