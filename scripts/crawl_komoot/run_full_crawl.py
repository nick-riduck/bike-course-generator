#!/usr/bin/env python3
"""
Komoot Full Crawler - 880개 코스 전체 크롤링
Based on run_test_crawl.py (검증 완료된 로직)

흐름:
1. 수동 로그인 & Discover 페이지 셋업
2. 카드 클릭 → 오버레이에서 smarttour URL 추출
3. 새 탭으로 상세페이지 열기 → kmtBoot.setProps JSON 파싱 (metadata 전체 추출)
4. GPX 다운로드 (2-step modal)
5. 탭 닫기 → 다음 카드 / 다음 페이지

소요: ~10시간 (카드당 ~41초 딜레이)
출력: crawl_data/KOMOOT_FULL/{tour_id}/metadata.json + GPX
"""

import os
import re
import sys
import time
import json
import random
import logging
import requests
from datetime import datetime
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

# --- Configuration ---
OUTPUT_DIR = "crawl_data/KOMOOT_FULL"
TOTAL_TARGET = 880
TOTAL_DURATION_HOURS = 10
DELAY_PER_CARD = (TOTAL_DURATION_HOURS * 3600) / TOTAL_TARGET  # ~41 seconds
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "_progress.json")

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(OUTPUT_DIR, "crawl.log") if os.path.exists(OUTPUT_DIR) else "crawl.log",
                            encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


# =============================================================================
# Driver Setup
# =============================================================================

COOKIE_FILE = os.path.join(OUTPUT_DIR, "_cookies.json")


def setup_driver(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
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
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def save_cookies(driver):
    """Save browser cookies to file."""
    with open(COOKIE_FILE, "w") as f:
        json.dump(driver.get_cookies(), f)
    log.info(f"Cookies saved to {COOKIE_FILE}")


def load_cookies(driver):
    """Load cookies from file into driver."""
    driver.get("https://www.komoot.com")  # Need to be on domain first
    time.sleep(2)
    with open(COOKIE_FILE, "r") as f:
        cookies = json.load(f)
    for cookie in cookies:
        # Remove problematic fields
        cookie.pop("sameSite", None)
        cookie.pop("storeId", None)
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
    log.info(f"Loaded {len(cookies)} cookies.")
    driver.refresh()
    time.sleep(3)


def random_sleep(base, variance=0.3):
    """Sleep with random jitter to mimic human behavior."""
    duration = random.uniform(base * (1 - variance), base * (1 + variance))
    time.sleep(duration)


# =============================================================================
# Progress Tracking (resume 지원)
# =============================================================================

def load_progress():
    """Load set of already-processed tour IDs for resume support."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return set(json.load(f).get("processed_ids", []))
    return set()


def save_progress(processed_ids):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({
            "processed_ids": list(processed_ids),
            "count": len(processed_ids),
            "updated_at": datetime.now().isoformat(),
        }, f, indent=2)


# =============================================================================
# Page Navigation
# =============================================================================

def get_cards(driver):
    """Find tour cards on the current page."""
    return driver.find_elements(By.CSS_SELECTOR, "div.css-dq6gmh")


def try_next_page(driver):
    """Click the 'Next Page' pagination button."""
    log.info("[Pagination] Looking for Next Page button...")
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, "button.css-btlqyj")
        if not btns:
            log.warning("[Pagination] No pagination buttons found.")
            return False

        next_btn = btns[-1]  # Last button is typically 'next'
        if next_btn.is_displayed() and next_btn.is_enabled():
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", next_btn)
            log.info("[Pagination] Clicked Next Page. Waiting for load...")
            time.sleep(5)
            return True
        else:
            log.warning("[Pagination] Button found but not clickable (last page?).")
            return False
    except Exception as e:
        log.error(f"[Pagination] Error: {e}")
        return False


# =============================================================================
# Image URL Helper
# =============================================================================

def _clean_image_url(src, width=1920):
    """Convert templated image URL to a usable URL."""
    if not src:
        return None
    src = src.replace("{width}", str(width)).replace("{height}", "").replace("{crop}", "false")
    src = re.sub(r'&height=(?=&|$)', '', src)
    return src


# =============================================================================
# Data Extraction from Embedded JSON
# =============================================================================

def _extract_from_embedded_json(page_source):
    """Extract the kmtBoot.setProps() JSON from page source."""
    match = re.search(r'kmtBoot\.setProps\("(.+?)"\);', page_source, re.DOTALL)
    if not match:
        return None
    escaped = match.group(1)
    unescaped = json.loads('"' + escaped + '"')
    return json.loads(unescaped)


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

    # Gallery (user photos)
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

        # Tips
        tips_container = ref_emb.get("tips", {})
        if isinstance(tips_container, dict):
            for tip in (tips_container.get("_embedded", {}).get("items") or []):
                creator = tip.get("_embedded", {}).get("creator", {})
                wp_data["tips"].append({
                    "text": tip.get("text", ""),
                    "author": creator.get("display_name", ""),
                })

        # Waypoint images
        imgs_container = ref_emb.get("images", {})
        if isinstance(imgs_container, dict):
            for img in (imgs_container.get("_embedded", {}).get("items") or []):
                src = img.get("src", "")
                if src:
                    wp_data["images"].append({"id": img.get("id"), "src": _clean_image_url(src)})

        data["waypoints"].append(wp_data)

    # Way Types & Surfaces (segment-level)
    data["way_types"] = (tour_emb.get("way_types") or {}).get("items") or []
    data["surfaces"] = (tour_emb.get("surfaces") or {}).get("items") or []

    return data


def _extract_from_html(page_source, tour_id, real_url):
    """Fallback: scrape from rendered HTML if embedded JSON not available."""
    soup = BeautifulSoup(page_source, "html.parser")
    data = {
        "tour_id": tour_id, "url": real_url, "title": "", "stats": {},
        "description": "", "images": [], "waypoints": [],
    }
    title_tag = soup.find("h1")
    if title_tag:
        data["title"] = title_tag.text.strip()

    for stat in soup.find_all("div", attrs={"data-test-id": re.compile(r"t_distance|t_duration|t_elevation")}):
        key = stat.get("data-test-id")
        val = stat.find(attrs={"data-test-id": re.compile(r".*_value$")}) or stat.find("p")
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


# =============================================================================
# Detail Page Processing (metadata + GPX download)
# =============================================================================

def extract_data_from_detail_page(driver, real_url):
    """Extract metadata from detail page using embedded JSON, then download GPX."""
    time.sleep(3)

    tour_id = real_url.split("smarttour/")[1].split("?")[0] if "smarttour/" in real_url else \
              real_url.split("tour/")[1].split("?")[0] if "tour/" in real_url else "unknown_id"

    page_source = driver.page_source
    props = _extract_from_embedded_json(page_source)

    if props:
        data = _extract_from_props(props, tour_id, real_url)
    else:
        log.warning(f"[{tour_id}] kmtBoot.setProps not found, falling back to HTML scraping")
        data = _extract_from_html(page_source, tour_id, real_url)

    wp_count = len(data.get("waypoints", []))
    img_count = len(data.get("images", []))
    log.info(f"[{tour_id}] Extracted: {data['title']} | {wp_count} waypoints | {img_count} images")

    # Save metadata
    tour_dir = os.path.join(OUTPUT_DIR, tour_id)
    os.makedirs(tour_dir, exist_ok=True)
    with open(os.path.join(tour_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Set GPX download path to tour directory via CDP
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": os.path.abspath(tour_dir),
    })

    # Download GPX via two-step modal
    _download_gpx(driver, tour_id)

    # Download images (cover + waypoint images) — uses CDN, not komoot server
    _download_images(data, tour_dir)

    return tour_id


def _download_gpx(driver, tour_id):
    """Click GPX download button → wait for modal → click Download."""
    try:
        log.info(f"[{tour_id}] Looking for GPX Download button...")
        dl_xpath = "//a[@aria-label='GPX 다운로드'] | //a[@aria-label='Download GPX']"
        initial_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, dl_xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", initial_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", initial_btn)
        log.info(f"[{tour_id}] Clicked GPX button. Waiting for modal...")

        time.sleep(2)
        modal_dl_xpath = "//a[@aria-label='Download' or @aria-label='다운로드']"
        final_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, modal_dl_xpath)))
        driver.execute_script("arguments[0].click();", final_btn)

        log.info(f"[{tour_id}] GPX download started.")
        time.sleep(5)  # Wait for download to complete

    except Exception as e:
        log.error(f"[{tour_id}] GPX download failed: {e}")


def _download_images(data, tour_dir):
    """Download cover images and waypoint images to tour_dir/images/."""
    tour_id = data.get("tour_id", "?")
    images_dir = os.path.join(tour_dir, "images")

    # Collect all image URLs: cover + waypoint images
    all_images = []
    for img in (data.get("images") or []):
        src = img.get("src")
        if src:
            all_images.append(("cover", img.get("id"), src))

    for wp in (data.get("waypoints") or []):
        for img in (wp.get("images") or []):
            src = img.get("src")
            if src:
                all_images.append(("wp", img.get("id"), src))

    if not all_images:
        return

    os.makedirs(images_dir, exist_ok=True)
    downloaded = 0

    for img_type, img_id, url in all_images:
        try:
            # Determine filename: cover_123.jpg or wp_456.jpg
            ext = "jpg"
            fname = f"{img_type}_{img_id}.{ext}" if img_id else f"{img_type}_{downloaded}.{ext}"
            fpath = os.path.join(images_dir, fname)

            if os.path.exists(fpath):
                downloaded += 1
                continue

            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                with open(fpath, "wb") as f:
                    f.write(resp.content)
                downloaded += 1
            else:
                log.warning(f"[{tour_id}] Image {fname} failed: HTTP {resp.status_code}")
        except Exception as e:
            log.warning(f"[{tour_id}] Image download error: {e}")

    log.info(f"[{tour_id}] Downloaded {downloaded}/{len(all_images)} images.")


# =============================================================================
# Card Processing
# =============================================================================

def process_card(driver, card_element, card_idx, page_num, processed_ids):
    """
    Click card → extract URL from overlay → open detail in new tab →
    extract metadata + download GPX → close tab → close overlay.
    """
    log.info(f"[Page {page_num} - Card {card_idx}] Processing...")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_element)
    time.sleep(1)

    # 1. Click card to open overlay
    try:
        ActionChains(driver).move_to_element(card_element).click().perform()
        time.sleep(3)
    except Exception as e:
        log.error(f"[Page {page_num} - Card {card_idx}] Failed to click card: {e}")
        return None

    # 2. Extract smarttour URL from overlay
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

    tour_id = None

    if not real_url:
        log.error(f"[Page {page_num} - Card {card_idx}] No valid URL found in overlay.")
    else:
        candidate_id = real_url.split("smarttour/")[1].split("?")[0] if "smarttour/" in real_url else \
                        real_url.split("tour/")[1].split("?")[0] if "tour/" in real_url else None
        if candidate_id and candidate_id in processed_ids:
            log.info(f"[{candidate_id}] Already processed, skipping.")
        else:
            # 3. Open detail page in new tab
            original_window = driver.current_window_handle
            try:
                log.info(f"  -> Opening: {real_url}")
                driver.execute_script(f"window.open('{real_url}', '_blank');")
                time.sleep(2)
                driver.switch_to.window(driver.window_handles[-1])

                tour_id = extract_data_from_detail_page(driver, real_url)

                driver.close()
                driver.switch_to.window(original_window)
                log.info(f"  -> Detail page processed and closed.")
            except Exception as e:
                log.error(f"  -> Detail page error: {e}")
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                    driver.switch_to.window(original_window)
                except:
                    pass

    # 4. Close overlay
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(2)
    except:
        pass

    return tour_id


# =============================================================================
# Main Loop
# =============================================================================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Re-init logging to file now that OUTPUT_DIR exists
    file_handler = logging.FileHandler(os.path.join(OUTPUT_DIR, "crawl.log"), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(file_handler)

    processed_ids = load_progress()
    log.info(f"Loaded progress: {len(processed_ids)} already processed.")

    print("\n" + "=" * 60)
    print("  KOMOOT FULL CRAWLER")
    print("=" * 60)
    print(f"  Target: {TOTAL_TARGET} courses")
    print(f"  Output: {OUTPUT_DIR}/")
    print(f"  Resume: {len(processed_ids)} already done")
    print(f"  Delay:  ~{DELAY_PER_CARD:.0f}s per card (~{TOTAL_DURATION_HOURS}h total)")
    print("=" * 60)
    print("\n1. Login manually in the browser.")
    print("2. Navigate to Discover and set your filters (max_distance 등).")
    print("3. Scroll down so the tour list loads.")
    print("4. Press ENTER when ready.")
    print("   → 브라우저가 최소화되고 백그라운드에서 크롤링 시작합니다.\n")

    driver = setup_driver(headless=False)
    driver.get("https://www.komoot.com/login")

    try:
        input(">>> Press ENTER to start crawling...")

        # Minimize browser window — no more focus stealing
        driver.minimize_window()

        # === Phase 2: Crawl Loop ===
        log.info("=== CRAWL STARTED ===")
        page_num = 1
        total_processed = len(processed_ids)
        errors_in_row = 0

        while total_processed < TOTAL_TARGET:
            time.sleep(2)

            cards = get_cards(driver)
            num_cards = len(cards)
            log.info(f"\n[Page {page_num}] Found {num_cards} cards.")

            if num_cards == 0:
                log.warning("No cards found. Trying to scroll...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                cards = get_cards(driver)
                num_cards = len(cards)
                if num_cards == 0:
                    if not try_next_page(driver):
                        log.warning("No cards and no next page. Waiting for manual intervention.")
                        input(">>> Fix the page and press ENTER to retry...")
                    continue

            for i in range(num_cards):
                if total_processed >= TOTAL_TARGET:
                    break

                # Re-fetch cards (DOM may have changed after overlay close)
                cards = get_cards(driver)
                if i >= len(cards):
                    log.warning(f"Card index {i} out of range (only {len(cards)} cards). Breaking.")
                    break

                card = cards[i]
                tour_id = process_card(driver, card, i + 1, page_num, processed_ids)

                if tour_id:
                    processed_ids.add(tour_id)
                    total_processed = len(processed_ids)
                    save_progress(processed_ids)
                    errors_in_row = 0

                    log.info(f"  ✓ Progress: {total_processed}/{TOTAL_TARGET} "
                             f"({total_processed/TOTAL_TARGET*100:.1f}%)")

                    # Human-like delay
                    delay = random.uniform(DELAY_PER_CARD * 0.7, DELAY_PER_CARD * 1.3)
                    log.info(f"  Sleeping {delay:.0f}s...")
                    time.sleep(delay)
                else:
                    errors_in_row += 1
                    if errors_in_row >= 5:
                        log.error("5 consecutive errors. Pausing for manual check.")
                        input(">>> Check the browser and press ENTER to continue...")
                        errors_in_row = 0
                    else:
                        random_sleep(5)

            # Next page
            if total_processed < TOTAL_TARGET:
                log.info(f"[Page {page_num}] Done. Moving to next page...")
                if not try_next_page(driver):
                    log.warning("Could not find Next Page button.")
                    input(">>> Navigate to next page manually, then press ENTER...")
                page_num += 1

        log.info(f"\n=== CRAWL COMPLETE: {total_processed} courses processed ===")

    except KeyboardInterrupt:
        log.info(f"\nStopped by user. Progress saved: {len(processed_ids)} courses.")
        save_progress(processed_ids)
    except Exception as e:
        log.error(f"\nCritical error: {e}")
        save_progress(processed_ids)
        raise
    finally:
        driver.quit()
        log.info("Driver closed.")


if __name__ == "__main__":
    main()
