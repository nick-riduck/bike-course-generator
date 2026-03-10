#!/usr/bin/env python3
"""
Dump page source to file for debugging
"""
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

START_URL = "https://www.komoot.com/discover/Current_location/@37.5049040,127.0640070/tours?sport=touringbicycle&map=true&max_distance=500&pageNumber=1"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def main():
    driver = setup_driver()
    try:
        print("Logging in phase... Please login manually.")
        driver.get("https://www.komoot.com/login")
        input("Press ENTER after login...")

        print(f"Navigating to {START_URL}")
        driver.get(START_URL)
        time.sleep(10) # Wait generous time for loading
        
        # Scroll down a bit
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        print("Saving page source to 'debug_page_source.html'...")
        with open("debug_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
            
        print("Done. Check debug_page_source.html")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
