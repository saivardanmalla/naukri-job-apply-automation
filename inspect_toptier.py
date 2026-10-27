from pathlib import Path
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager

BASE_DIR = Path(".").resolve()
profile_dir = BASE_DIR / "chrome_naukri_profile"
options = ChromeOptions()
options.add_argument(f"--user-data-dir={profile_dir}")
options.add_argument("--headless=new")
options.add_argument("--start-maximized")
service = ChromeService(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    driver.get("https://www.naukri.com/python-automation-engineer-jobs-in-bangalore?k=Python%20Automation%20Engineer&l=Bangalore")
    time.sleep(5)

    elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Quick apply')]")
    print(f"Quick apply elements found: {len(elements)}")
    if elements:
        # Find the card container
        card = elements[0]
        for i in range(4):
            card = card.find_element(By.XPATH, "..")
        print(f"Card tag: {card.tag_name}, class: {card.get_attribute('class')}")
        print("Card text:")
        print(card.text)
        print("="*40)
        # Find all clickable elements or title link in card
        links = card.find_elements(By.TAG_NAME, "a")
        print(f"Links inside card: {len(links)}")
        for l in links:
            print("Link text:", l.text, "| href:", l.get_attribute("href"))
        
        # Check all cards matching this card's class
        card_class = card.get_attribute("class")
        all_cards = driver.find_elements(By.XPATH, f"//*[contains(@class, '{card_class.split()[0]}')]")
        print(f"Total matching cards found: {len(all_cards)}")
finally:
    driver.quit()
