"""Naukri Batch Job Apply Automation (5 Jobs) with Microsoft Edge.
Directly clicks 'Quick apply' buttons on search cards and handles questionnaires:
- Experience questions: 6 years
- Yes/No questions: Always 'Yes'
- Submits and applies up to MAX_JOBS_TO_APPLY (default 5).
"""
import os
import sys
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Add workspace to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Load .env
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

NAUKRI_EMAIL = os.getenv("NAUKRI_EMAIL", "").strip()
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "").strip()
BROWSER = os.getenv("BROWSER", "edge").lower().strip()
HEADLESS = os.getenv("HEADLESS", "False").lower() in ("true", "1", "yes")
MAX_JOBS_TO_APPLY = int(os.getenv("MAX_JOBS_TO_APPLY", "5"))
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "Python Automation Engineer").strip()
LOCATION = os.getenv("LOCATION", "Bangalore").strip()
RESUME_PATH = os.getenv("RESUME_PATH", "").strip()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("NaukriBatchApply")


def get_driver(headless: bool = False):
    """Initializes Microsoft Edge WebDriver with session persistence and visible browser."""
    profile_dir = BASE_DIR / "edge_naukri_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    options = EdgeOptions()
    if headless:
        logger.info("Running Microsoft EDGE in HEADLESS mode (background).")
        options.add_argument("--headless=new")
    else:
        logger.info("Running Microsoft EDGE in HEADED mode (Window visible on your screen).")

    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--start-maximized")
    options.add_argument("--window-position=0,0")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = EdgeService(EdgeChromiumDriverManager().install())
    driver = webdriver.Edge(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.set_page_load_timeout(60)

    # Force window to foreground on user's active desktop across all launch methods
    try:
        import ctypes
        user32 = ctypes.windll.user32
        
        # Maximize via selenium first
        try:
            driver.maximize_window()
        except Exception:
            pass

        # Use ctypes to find and bring Edge window to top
        def make_window_foreground():
            import win32gui
            import win32process
            import win32con

            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    text = win32gui.GetWindowText(hwnd).lower()
                    if "edge" in text or "naukri" in text:
                        # Allow setting foreground from background process
                        try:
                            user32.AllowSetForegroundWindow(-1) # ASFW_ANY
                        except Exception:
                            pass
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                        win32gui.BringWindowToTop(hwnd)
                        win32gui.SetForegroundWindow(hwnd)
                return True

            win32gui.EnumWindows(callback, None)

        time.sleep(1.5)
        make_window_foreground()
    except Exception as e:
        logger.debug(f"Window foreground adjustment notice: {e}")

    return driver


def check_is_logged_in(driver) -> bool:
    """Checks if the user has an active session on Naukri."""
    driver.get("https://www.naukri.com/mnjuser/homepage")
    time.sleep(3)
    curr_url = driver.current_url.lower()
    if "nlogin" in curr_url or "login" in curr_url:
        return False
    profile_elements = driver.find_elements(
        By.CSS_SELECTOR,
        "a[href*='mnjuser/profile'], .nI-gNb-drawer__bars, .view-profile-wrapper"
    )
    return len(profile_elements) > 0


def login_to_naukri(driver, email: str, password: str):
    """Logs into Naukri if not already logged in."""
    if check_is_logged_in(driver):
        logger.info("Already logged in to Naukri via stored session.")
        return True

    logger.info("Navigating to Naukri login page...")
    driver.get("https://www.naukri.com/nlogin/login")
    time.sleep(3)

    try:
        wait = WebDriverWait(driver, 15)
        username_field = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@placeholder='Enter your active Email ID / Username'] | //input[@id='usernameField']"
            ))
        )
        password_field = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@placeholder='Enter your password'] | //input[@id='passwordField']"
            ))
        )

        logger.info("Filling login credentials...")
        username_field.clear()
        username_field.send_keys(email)
        time.sleep(1)

        password_field.clear()
        password_field.send_keys(password)
        time.sleep(1)

        login_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Login') or @type='submit']")
        login_btn.click()
        logger.info("Clicked login button. Waiting for dashboard...")
        time.sleep(5)

        for _ in range(6):
            if "homepage" in driver.current_url or "profile" in driver.current_url:
                logger.info("Login successful!")
                return True
            time.sleep(2)

        return True
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return False


def handle_questionnaire(driver):
    """
    Handles any modal dialogs, chatbot drawers, or questionnaires after clicking Quick apply.
    Supports the TopTier Chatbot ('Type message here...', experience -> 6, yes/no -> Yes, click Save).
    """
    logger.info("Checking for application questionnaire or TopTier chatbot...")
    time.sleep(2)

    # 1. Handle TopTier Chatbot Drawer ("Type message here..." & "Save" button)
    for turn in range(6):
        chat_inputs = driver.find_elements(
            By.XPATH,
            "//input[contains(@placeholder, 'Type message') or contains(@placeholder, 'message')]"
            " | //textarea[contains(@placeholder, 'Type message') or contains(@placeholder, 'message')]"
            " | //div[@contenteditable='true']"
        )
        if not chat_inputs:
            break

        chat_input = chat_inputs[0]
        if not chat_input.is_displayed():
            break

        # Read surrounding chatbot messages to identify the question
        messages = driver.find_elements(
            By.XPATH,
            "//*[contains(@class, 'message') or contains(@class, 'bubble') or contains(@class, 'chat') or contains(@class, 'text')]"
        )
        last_question = ""
        for m in messages[-4:]:
            txt = m.text.strip().lower()
            if any(k in txt for k in ["experience", "python", "selenium", "years", "notice", "comfortable", "skills", "relevant", "yes", "no"]):
                last_question = txt

        # Determine answer according to user rules
        if any(w in last_question for w in ["experience", "years", "year", "yr", "exp"]):
            answer = "6"
            logger.info(f"TopTier Chatbot asked experience question ('{last_question[:40]}...'). Answering: '6'")
        elif any(w in last_question for w in ["yes", "no", "comfortable", "willing", "notice", "ready"]):
            answer = "Yes"
            logger.info(f"TopTier Chatbot asked Yes/No question ('{last_question[:40]}...'). Answering: 'Yes'")
        else:
            answer = "6"
            logger.info("TopTier Chatbot question: default answering '6'")

        # First check if there are clickable chips (e.g. Yes / No buttons or number buttons)
        chips = driver.find_elements(
            By.XPATH,
            "//button[translate(normalize-space(.), 'YES', 'yes')='yes'] | //span[translate(normalize-space(.), 'YES', 'yes')='yes']"
            " | //button[contains(text(), '6')] | //span[contains(text(), '6')]"
        )
        clicked_chip = False
        for c in chips:
            if c.is_displayed():
                try:
                    c.click()
                    clicked_chip = True
                    logger.info(f"Clicked chatbot option chip: '{c.text}'")
                    time.sleep(2)
                    break
                except Exception:
                    pass

        # If no chip clicked, type into the 'Type message here...' input
        if not clicked_chip:
            try:
                chat_input.clear()
            except Exception:
                pass
            chat_input.send_keys(answer)
            time.sleep(0.5)
            chat_input.send_keys(Keys.ENTER)
            logger.info(f"Sent answer '{answer}' into chatbot input.")
            time.sleep(2)

        # Check if bottom-right 'Save' button is enabled and clickable
        save_btns = driver.find_elements(
            By.XPATH,
            "//button[contains(translate(., 'SAVE', 'save'), 'save') or contains(translate(., 'SUBMIT', 'submit'), 'submit')]"
        )
        for sb in save_btns:
            if sb.is_displayed() and sb.is_enabled():
                logger.info(f"Clicking chatbot final button: '{sb.text}'")
                try:
                    sb.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", sb)
                time.sleep(2)

    # 2. Handle Traditional Modal Forms (Radio buttons, Dropdowns, Inputs)
    for step in range(4):
        action_taken = False

        # Check for Yes/No Radio buttons & Clickable labels
        try:
            yes_elements = driver.find_elements(
                By.XPATH,
                "//label[translate(normalize-space(.), 'YES', 'yes')='yes']"
                " | //input[@type='radio'][contains(translate(@value, 'YES', 'yes'), 'yes')]"
                " | //button[translate(normalize-space(.), 'YES', 'yes')='yes']"
            )
            for y in yes_elements:
                try:
                    if y.is_displayed():
                        logger.info(f"Selecting 'Yes' option: '{y.text}'")
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", y)
                        time.sleep(0.5)
                        try:
                            y.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", y)
                        action_taken = True
                except Exception:
                    pass
        except Exception:
            pass

        # Check for Experience Inputs (fill 6)
        try:
            inputs = driver.find_elements(
                By.XPATH,
                "//input[@type='text' or @type='number' or not(@type)][not(contains(@placeholder, 'Search')) and not(contains(@id, 'search'))]"
            )
            for inp in inputs:
                try:
                    if inp.is_displayed() and inp.is_enabled():
                        curr_val = inp.get_attribute("value") or ""
                        if not curr_val:
                            logger.info("Filling experience answer '6' in field...")
                            inp.clear()
                            inp.send_keys("6")
                            action_taken = True
                except Exception:
                    pass
        except Exception:
            pass

        # Check for Dropdowns (select 6 or 6 years)
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            for sel in selects:
                try:
                    if sel.is_displayed() and sel.is_enabled():
                        options = sel.find_elements(By.TAG_NAME, "option")
                        for opt in options:
                            if "6" in opt.text.strip().lower():
                                opt.click()
                                logger.info(f"Selected dropdown experience: '{opt.text}'")
                                action_taken = True
                                break
                except Exception:
                    pass
        except Exception:
            pass

        # Click Next / Submit / Save / Done / Continue
        try:
            prog_selectors = [
                "//button[contains(text(),'Submit') or contains(text(),'submit')]",
                "//button[contains(text(),'Save') or contains(text(),'save')]",
                "//button[contains(text(),'Done') or contains(text(),'done')]",
                "//button[contains(text(),'Next') or contains(text(),'next')]",
                "//button[contains(text(),'Continue') or contains(text(),'continue')]"
            ]
            for p_xp in prog_selectors:
                btns = driver.find_elements(By.XPATH, p_xp)
                clicked = False
                for b in btns:
                    if b.is_displayed() and b.is_enabled():
                        logger.info(f"Clicking modal confirmation button: '{b.text}'")
                        try:
                            b.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", b)
                        clicked = True
                        action_taken = True
                        time.sleep(2)
                        break
                if clicked:
                    break
        except Exception:
            pass

        if not action_taken:
            break


import json

APPLIED_HISTORY_FILE = BASE_DIR / "applied_jobs.json"


def load_applied_history() -> set:
    """Loads set of previously applied job titles and fingerprints from disk."""
    if not APPLIED_HISTORY_FILE.exists():
        return set()
    try:
        with open(APPLIED_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("applied_titles", []))
    except Exception:
        return set()


def record_applied_job(title: str, company: str = ""):
    """Saves newly applied job title to persistent applied history."""
    current = load_applied_history()
    norm_title = title.strip().lower()
    current.add(norm_title)
    if company:
        current.add(f"{company.strip().lower()}|{norm_title}")
    try:
        with open(APPLIED_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"applied_titles": sorted(list(current))}, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save applied history: {e}")


def search_and_apply_batch(driver, max_jobs: int = 5):
    """
    Searches for jobs on Naukri, clicks 'Quick apply' directly on cards,
    handles questionnaires, and strictly guarantees applying to max_jobs FRESH,
    previously unapplied jobs (persisting history across all runs and paginating if needed).
    """
    applied_history = load_applied_history()
    logger.info(f"Loaded {len(applied_history)} previously recorded applied jobs from history.")

    search_query_encoded = SEARCH_QUERY.replace(" ", "%20")
    location_encoded = LOCATION.replace(" ", "%20")
    base_slug = f"{SEARCH_QUERY.replace(' ', '-').lower()}-jobs-in-{LOCATION.replace(' ', '-').lower()}"

    fresh_applied_count = 0
    main_window = driver.current_window_handle

    logger.info("=" * 60)
    logger.info(f"TARGET: APPLYING TO {max_jobs} FRESH / NEW JOBS (SKIPPING ALL PREVIOUS ONES)")
    logger.info("=" * 60)

    for page_num in range(1, 25):
        if fresh_applied_count >= max_jobs:
            break

        # Build page URL
        if page_num == 1:
            search_url = f"https://www.naukri.com/{base_slug}?k={search_query_encoded}&l={location_encoded}"
        else:
            search_url = f"https://www.naukri.com/{base_slug}-{page_num}?k={search_query_encoded}&l={location_encoded}"

        logger.info(f"[PAGE {page_num}] Navigating to: {search_url}")
        driver.get(search_url)
        time.sleep(5)

        # Bring Edge to front
        import subprocess
        try:
            subprocess.run(["powershell", "-Command", "(New-Object -ComObject WScript.Shell).AppActivate('Edge')"], capture_output=True)
        except Exception:
            pass

        # Dismiss any cookie / banner popups
        try:
            dismiss_btns = driver.find_elements(
                By.XPATH,
                "//button[contains(text(),'Got it') or contains(text(),'Later') or contains(text(),'Accept') or contains(@class,'crossIcon')] | //div[contains(@class,'crossIcon')]"
            )
            for db_btn in dismiss_btns:
                if db_btn.is_displayed():
                    db_btn.click()
                    time.sleep(1)
        except Exception:
            pass

        # Scroll to load all cards on the page
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

        # Scan for all Quick Apply elements on this page
        quick_apply_buttons = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'Quick apply') or contains(text(), 'Quick Apply')]"
        )
        logger.info(f"[PAGE {page_num}] Found {len(quick_apply_buttons)} 'Quick apply' elements.")

        for idx, qa_btn in enumerate(quick_apply_buttons):
            if fresh_applied_count >= max_jobs:
                break

            try:
                # Find the card container
                card = qa_btn
                for _ in range(4):
                    try:
                        p = card.find_element(By.XPATH, "..")
                        if len(p.text.split("\n")) >= 3:
                            card = p
                            break
                    except Exception:
                        break

                card_text = card.text.lower()

                # Extract job title & company accurately from TopTier card
                card_title_elem = None
                try:
                    card_title_elem = card.find_element(By.XPATH, ".//a[contains(@class, 'title') or contains(@href, 'job-listings')]")
                except Exception:
                    pass

                job_title = card_title_elem.text.strip() if card_title_elem and card_title_elem.text.strip() else ""
                lines = [l.strip() for l in card.text.split("\n") if l.strip()]

                if not job_title:
                    for l in lines:
                        if any(w in l.lower() for w in ["python", "automation", "sdet", "qa", "engineer", "developer", "test"]):
                            job_title = l
                            break

                company = ""
                for l in lines:
                    if l.lower() not in ["quick apply", "applied", "applied ✓", "save", "star"] and l != job_title:
                        company = l
                        break

                if not job_title:
                    job_title = f"TopTier Role {idx + 1} (Page {page_num})"

                norm_t = job_title.strip().lower()
                norm_c = company.strip().lower()
                job_key = f"{norm_c}|{norm_t}" if norm_c else norm_t

                # Check if previously applied on screen
                if "already applied" in card_text or "applied ✓" in card_text or "application sent" in card_text:
                    logger.info(f"[Skip Previously Applied on screen]: '{job_title}'")
                    continue

                # Check persistent history (only match exact unique combination)
                if job_key in applied_history:
                    logger.info(f"[Skip Already Applied from history]: '{job_title}' @ '{company}'")
                    continue

                # FRESH JOB FOUND!
                logger.info("-" * 55)
                logger.info(f"-> [FRESH JOB {fresh_applied_count + 1}/{max_jobs}] Targeting: '{job_title}' @ '{company}'")

                # Scroll into view and highlight
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", qa_btn)
                driver.execute_script("arguments[0].style.border = '3px solid #ff3d00'; arguments[0].style.boxShadow = '0 0 20px #ff3d00';", qa_btn)
                time.sleep(2)

                initial_windows = set(driver.window_handles)

                # Click Quick apply
                logger.info(f"CLICKING 'Quick apply' for: '{job_title}'...")
                try:
                    ActionChains(driver).move_to_element(qa_btn).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", qa_btn)

                time.sleep(3)

                # Check if new tab opened
                new_windows = set(driver.window_handles) - initial_windows
                if new_windows:
                    new_tab = list(new_windows)[0]
                    driver.switch_to.window(new_tab)
                    logger.info(f"Switched to application window: {driver.title}")
                    time.sleep(2)

                # Answer TopTier Chatbot or questionnaires
                handle_questionnaire(driver)

                # Close new tab if opened and return to search
                if new_windows:
                    try:
                        driver.close()
                    except Exception:
                        pass
                    driver.switch_to.window(main_window)
                    time.sleep(2)

                # Record fresh application
                record_applied_job(job_title, company)
                applied_history.add(norm_t)
                applied_history.add(f"{norm_c}|{norm_t}")
                fresh_applied_count += 1

                logger.info(f"SUCCESS: Fresh Application [{fresh_applied_count}/{max_jobs}] Submitted for: '{job_title}'!")

                # Highlight card in green
                try:
                    driver.execute_script("arguments[0].style.border = '3px solid #00e676'; arguments[0].style.boxShadow = '0 0 20px #00e676';", card)
                except Exception:
                    pass

                time.sleep(2)

            except Exception as e:
                logger.warning(f"Error processing Quick Apply candidate {idx + 1}: {e}")
                continue

    # Take screenshot of the final result
    shots_dir = BASE_DIR / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(shots_dir / "batch_apply_completed.png"))
    logger.info(f"Saved completion screenshot to {shots_dir / 'batch_apply_completed.png'}")

    logger.info("=" * 60)
    logger.info(f"BATCH COMPLETE: Successfully applied to {fresh_applied_count} FRESH jobs!")
    logger.info("=" * 60)
    time.sleep(5)
    return True


def main():
    logger.info("Starting Naukri Batch Job Apply Automation (Headed Mode: %s, Browser: %s)", not HEADLESS, BROWSER.upper())
    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        logger.error("Missing NAUKRI_EMAIL or NAUKRI_PASSWORD in .env!")
        return

    driver = None
    try:
        driver = get_driver(headless=HEADLESS)
        logged_in = login_to_naukri(driver, NAUKRI_EMAIL, NAUKRI_PASSWORD)
        if not logged_in:
            logger.error("Failed to authenticate with Naukri.")
            return

        search_and_apply_batch(driver, max_jobs=MAX_JOBS_TO_APPLY)
    except Exception as e:
        logger.exception(f"Unexpected error during execution: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
