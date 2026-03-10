#!/usr/bin/env python3
"""
Detail Page HTML Dumper
1. Login to Komoot.
2. Navigate directly to a specific detail page.
3. Save the full HTML source for analysis.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def main():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("=== Komoot Detail Page HTML Dumper ===")
        driver.get("https://www.komoot.com/login")
        input("1. Please log in manually, then press ENTER to continue...")
        
        target_url = "https://www.komoot.com/ko-kr/smarttour/21955729?tour_origin=smart_tour_search"
        print(f"2. Navigating to {target_url} ...")
        driver.get(target_url)
        
        # Scroll a bit to load lazy images
        for i in range(5):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)
            
        time.sleep(3) # Wait for network requests
        
        html = driver.page_source
        filename = "debug_detail_page.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
            
        print(f"  [SUCCESS] Saved full HTML to: {filename}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
