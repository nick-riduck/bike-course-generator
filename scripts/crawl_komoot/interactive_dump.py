#!/usr/bin/env python3
"""
Interactive HTML Dumper
- Opens Chrome with Selenium.
- Lets you navigate and log in manually.
- Every time you press ENTER in the terminal, it saves the current DOM (HTML) to a file.
- Type 'q' and ENTER to quit.
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
    # Uncomment if you want to reuse your normal Chrome profile to keep login state:
    # chrome_options.add_argument("user-data-dir=/tmp/komoot_chrome_profile")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("\n=== Komoot HTML Capture Tool ===")
        print("1. Chrome browser is opening...")
        driver.get("https://www.komoot.com/discover")
        print("2. Please log in and navigate to the list or overlay you want to inspect.")
        print("================================\n")
        
        count = 1
        while True:
            user_input = input(f"▶ Press [ENTER] to capture current HTML (or type 'q' to quit) [Capture #{count}]: ")
            if user_input.strip().lower() == 'q':
                break
            
            filename = f"debug_komoot_{count}.html"
            html_content = driver.page_source
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"  [SUCCESS] Saved current page structure to: {filename}")
            count += 1

    finally:
        driver.quit()
        print("Browser closed.")

if __name__ == "__main__":
    main()
