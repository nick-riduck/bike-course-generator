#!/usr/bin/env python3
"""
Step 2: TRUE Overlay Automation Crawler (Based on Actual HTML Structure)
- Finds `div[data-test-id="tours-list"]`
- Iterates over its child `div` elements (the actual tour cards).
- Clicks the card to open the overlay.
- Finds the true `smarttour` URL from the Share link inside the overlay.
- Clicks Download GPX.
- Clicks Close to return to the list, then processes the next card.
"""

import os
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

OUTPUT_DIR = "crawl_data/KOMOOT_OVERLAY"
TOTAL_TARGET = 880

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

def try_next_page(driver):
    print("  [Pagination] Looking for 'Next Page' button...")
    xpaths = [
        "//button[@aria-label='Next page']",
        "//button[@aria-label='다음 페이지']",
        "//*[local-name()='svg']/*[local-name()='path' and contains(@d, 'M15.8334 10.4017L10.0001 16.235')]/ancestor::button"
    ]
    for xp in xpaths:
        try:
            btns = driver.find_elements(By.XPATH, xp)
            for btn in btns:
                if btn.is_displayed() and btn.is_enabled():
                    print(f"  [Pagination] Clicking Next Page via xpath...")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(5) # Wait for page to load
                    return True
        except:
            pass
    return False

def get_cards(driver):
    return driver.find_elements(By.XPATH, "//div[@data-test-id='tours-list']/div")

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    driver = setup_driver()
    processed_urls = set()
    
    try:
        print("\n=== PHASE 1: LOGIN & SETUP ===")
        print("1. Login manually.")
        print("2. Navigate to Discover and setup your view.")
        print("3. Scroll down so the list loads.")
        print("4. Press ENTER when the list is completely ready.")
        driver.get("https://www.komoot.com/login")
        input()
        
        print("\n=== PHASE 2: AUTOMATION START ===")
        
        count = 0
        while count < TOTAL_TARGET:
            
            time.sleep(2) # wait for list rendering
            
            # 1. Get cards on this page
            cards = get_cards(driver)
            num_cards = len(cards)
            print(f"\n[Scan] Found {num_cards} tour cards on this page.")
            
            if num_cards == 0:
                print("  -> No cards found. Attempting to scroll...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                if not try_next_page(driver):
                    input("Press ENTER to retry scanning, or CTRL+C to stop.")
                continue

            # 2. Iterate and click each card
            for i in range(num_cards):
                if count >= TOTAL_TARGET: break
                
                cards = get_cards(driver)
                if i >= len(cards): break
                card = cards[i]
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                time.sleep(1)

                print(f"\n[{count+1}/{TOTAL_TARGET}] Processing Card {i+1}...")

                try:
                    # Click card to open OVERLAY
                    driver.execute_script("arguments[0].click();", card)
                    time.sleep(4) # Wait for overlay
                    
                    # Inside Overlay (2번 HTML)
                    # Extract the true URL (smarttour)
                    true_url = "UNKNOWN"
                    try:
                        link_el = driver.find_element(By.XPATH, "//a[contains(@href, 'smarttour/') or contains(@href, 'tour/')]")
                        true_url = link_el.get_attribute('href')
                        print(f"    -> True URL identified: {true_url}")
                    except:
                        pass
                        
                    if true_url in processed_urls and true_url != "UNKNOWN":
                        print("    -> Already processed. Skipping download.")
                    else:
                        # Try Download GPX
                        try:
                            dl_xpath = "//a[@aria-label='GPX 다운로드'] | //a[@aria-label='Download GPX'] | //a[@aria-label='다운로드'] | //button[@aria-label='GPX 다운로드']"
                            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, dl_xpath)))
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", btn)
                            print("    -> Clicked Download GPX Button.")
                            
                            if true_url != "UNKNOWN":
                                processed_urls.add(true_url)
                            count += 1
                            time.sleep(2) # Wait for download
                        except:
                            print("    -> Download button NOT found in overlay.")

                    # Close Overlay
                    try:
                        close_xpath = "//button[@aria-label='Close' or @aria-label='닫기']"
                        close_btn = driver.find_element(By.XPATH, close_xpath)
                        driver.execute_script("arguments[0].click();", close_btn)
                        print("    -> Closed overlay.")
                        time.sleep(2)
                    except:
                        # Fallback: Press Escape to close overlay
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                        print("    -> Pressed Escape to close overlay.")
                        time.sleep(2)

                except Exception as e:
                    print(f"    -> Error processing card: {e}")
                
            # Move to next page after finishing all cards on current page
            if count < TOTAL_TARGET:
                if not try_next_page(driver):
                    print("  -> Could not find Next Page button. You may need to click it manually.")
                    input("Press ENTER after navigating to the next page.")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
