#!/usr/bin/env python3
"""
Step 1: Action Analyzer
- Monitors user actions to identify Selectors and URLs.
- DOES NOT crawl anything yet. Just reports what it sees.
"""

import time
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def analyze_current_page(driver):
    print("\n[Analysis] Scanning current page...")
    
    # 1. Analyze URL
    current_url = driver.current_url
    print(f"  Current URL: {current_url}")
    
    # 2. Look for Download Buttons
    keywords = ['gpx', 'download', 'export', 'gps', '내보내기', '다운로드']
    buttons = []
    
    # Search buttons and anchors
    for tag in ['a', 'button', 'div']:
        elements = driver.find_elements(By.TAG_NAME, tag)
        for el in elements:
            try:
                text = el.text.lower()
                href = el.get_attribute('href')
                aria = el.get_attribute('aria-label')
                
                matched = False
                if text and any(k in text for k in keywords): matched = True
                if href and any(k in href.lower() for k in keywords): matched = True
                if aria and any(k in aria.lower() for k in keywords): matched = True
                
                if matched:
                    buttons.append({
                        "tag": tag,
                        "text": text[:30],
                        "href": href,
                        "class": el.get_attribute('class'),
                        "xpath": get_xpath(driver, el)
                    })
            except: pass
            
    if buttons:
        print(f"  Found {len(buttons)} potential Download buttons:")
        for i, b in enumerate(buttons[:5]):
            print(f"    {i+1}. <{b['tag']}> Text='{b['text']}' Href='{b['href']}'")
    else:
        print("  No obvious download buttons found.")

    # 3. Analyze Visible Data
    print("  Visible Text Data (Sample):")
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line for line in body_text.split('\n') if line.strip()]
        for line in lines[:10]: # Show first 10 lines
            print(f"    - {line}")
    except:
        print("    (Could not read body text)")

def get_xpath(driver, element):
    """Generate a simplified xpath for an element"""
    return driver.execute_script("""
        gPt=function(c){
            if(c.id!==''){return'id("'+c.id+'")'}
            if(c===document.body){return c.tagName}
            var a=0;
            var e=c.parentNode.childNodes;
            for(var b=0;b<e.length;b++){
                var d=e[b];
                if(d===c){return gPt(c.parentNode)+'/'+c.tagName+'['+(a+1)+']'}
                if(d.nodeType===1&&d.tagName===c.tagName){a++}
            }
        };
        return gPt(arguments[0]);
    """, element)

def main():
    driver = setup_driver()
    try:
        print("\n=== STEP 1: SETUP ===")
        print("1. Login and navigate to the list page.")
        print("2. DO NOT click a tour yet.")
        print("Press ENTER when ready.")
        driver.get("https://www.komoot.com/login")
        input()
        
        print("\n=== STEP 2: LIST ANALYSIS ===")
        print("I am recording the URL of the LIST page.")
        list_url = driver.current_url
        print(f"List URL: {list_url}")
        print("Now, click ONE tour to go to details.")
        print("Press ENTER *AFTER* the details page loads.")
        input()
        
        print("\n=== STEP 3: DETAIL PAGE ANALYSIS ===")
        analyze_current_page(driver)
        
        print("\n=== STEP 4: DOWNLOAD ACTION ===")
        print("Now find and CLICK the download button.")
        print("Press ENTER *AFTER* the download starts (or dialog opens).")
        input()
        
        # Check if URL changed or if we can see the button now
        print("\n[Re-Analysis] Checking page state after your click...")
        analyze_current_page(driver)
        
        print("\nAnalysis Complete. Does the extracted info look correct?")
        
    finally:
        print("Closing driver...")
        driver.quit()

if __name__ == "__main__":
    main()
