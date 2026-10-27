"""Naukri daily apply bot (Microsoft Edge).

Every run applies to DAILY_TARGET (default 5) FRESH jobs you have never applied to, via Quick apply,
regardless of match score, and saves a screenshot of each job page showing the green "Applied ✓" button.

Search order (first priority = Bangalore):
    Bangalore last 1 day -> 3 days -> 7 days, then anywhere in India 1 -> 3 -> 7 days,
    then (only if still short) Bangalore / anywhere 15 days.
    Queries: SEARCH_QUERIES (default "python, python automation").

Flow per job:
    1. Search results: click the card's "Quick apply" -> the job page opens.
    2. Job page: if the bottom button already says "Applied ✓" -> ignore the job (already applied).
       Otherwise click its "Quick apply".
    3. The recruiter chatbot opens on the right: answer each question and press Save.
    4. Confirm the bottom button now says "Applied ✓", take the screenshot, move to the next job.
"""
import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import date, datetime
import gc
from pathlib import Path
from urllib.parse import quote, urlparse

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _env(name, default=""):
    return os.getenv(name, default).strip()


NAUKRI_EMAIL = _env("NAUKRI_EMAIL")
NAUKRI_PASSWORD = _env("NAUKRI_PASSWORD")
HEADLESS = _env("HEADLESS", "False").lower() in ("true", "1", "yes")
BROWSER = _env("BROWSER", "edge" if sys.platform == "win32" else "chrome").lower()
NAUKRI_COOKIES = _env("NAUKRI_COOKIES")
COOKIES_FILE = BASE_DIR / "cookies.json"

JOBS_PER_RUN = int(_env("JOBS_PER_RUN") or _env("DAILY_TARGET") or _env("MAX_JOBS_TO_APPLY") or "50")
if len(sys.argv) > 1 and sys.argv[1].isdigit():
    JOBS_PER_RUN = int(sys.argv[1])
UNLIMITED = _env("UNLIMITED", "False").lower() in ("true", "1", "yes") or JOBS_PER_RUN <= 0
QUERIES = [q.strip() for q in (_env("SEARCH_QUERIES") or _env("SEARCH_QUERY") or "Python Automation Engineer, Python, Python Automation, Python SDET, Selenium Automation Engineer, Selenium, Selenium Python, API Testing, API Automation, API Automation Engineer").split(",") if q.strip()]
LOCATION = _env("LOCATION", "")                 # empty = anywhere in India
for _i, _arg in enumerate(sys.argv):
    if _arg == "--location" and _i + 1 < len(sys.argv):
        LOCATION = sys.argv[_i + 1].strip()
    elif _arg.startswith("--location="):
        LOCATION = _arg.split("=", 1)[1].strip()
    elif _arg == "--no-location":
        LOCATION = ""
ANYWHERE_FALLBACK = _env("ANYWHERE_FALLBACK", "True").lower() in ("true", "1", "yes")
AGE_WINDOWS = [int(x) for x in _env("AGE_WINDOWS", "1,3,7,15").split(",") if x.strip()]
MAX_PAGES = int(_env("MAX_PAGES_PER_QUERY", "15"))
MAX_ATTEMPTS = 1000 if UNLIMITED else int(_env("MAX_ATTEMPTS_PER_RUN", str(max(500, JOBS_PER_RUN * 4))))
MAX_RUN_MINUTES = int(_env("MAX_RUN_MINUTES", "10" if _env("GITHUB_ACTIONS") else "0"))
MANUAL_LOGIN_WAIT = int(_env("MANUAL_LOGIN_WAIT_SECONDS", "180"))

# Candidate Resume & Questionnaire Auto-Fill Configuration
_raw_resume = _env("RESUME_PATH", "resume.pdf")
if os.path.exists(_raw_resume):
    RESUME_PATH = _raw_resume
elif (BASE_DIR / "resume.pdf").exists():
    RESUME_PATH = str(BASE_DIR / "resume.pdf")
elif Path("resume.pdf").exists():
    RESUME_PATH = str(Path("resume.pdf").resolve())
else:
    RESUME_PATH = _raw_resume
PAN_NUMBER = _env("PAN", "")
CANDIDATE_NAME = _env("CANDIDATE_NAME", "")
CANDIDATE_FIRST_NAME = _env("CANDIDATE_FIRST_NAME", "")
CANDIDATE_LAST_NAME = _env("CANDIDATE_LAST_NAME", "")
CANDIDATE_PHONE = _env("CANDIDATE_PHONE", "")
CANDIDATE_EMAIL = _env("CANDIDATE_EMAIL", "")
CURRENT_COMPANY = _env("CURRENT_COMPANY", "")
CURRENT_DESIGNATION = _env("CURRENT_DESIGNATION", "")
PREVIOUS_COMPANY = _env("PREVIOUS_COMPANY", "")
PREVIOUS_DESIGNATION = _env("PREVIOUS_DESIGNATION", "")
EDUCATION_DEGREE = _env("DEGREE", "B.Tech")
EDUCATION_STREAM = _env("EDUCATION_STREAM", "Engineering")
COLLEGE_NAME = _env("COLLEGE", "")
GRADUATION_YEAR = _env("GRADUATION_YEAR", "2020")
GRADUATION_PERCENTAGE = _env("GRADUATION_PERCENTAGE", "85%")
LINKEDIN_URL = _env("LINKEDIN_URL", "")
GITHUB_URL = _env("GITHUB_URL", "")

EXPERIENCE_YEARS = _env("EXPERIENCE_YEARS", "6")
SKILLS = _env("SKILLS", "Python, Selenium, API Testing, Java, Selenide, Robot Framework, REST Assured, CI/CD, Jenkins, Git")
PREFERRED_LOCATION = _env("PREFERRED_LOCATION") or LOCATION
NOTICE_PERIOD = _env("NOTICE_PERIOD", "30")
CURRENT_CTC = _env("CURRENT_CTC", "30")
EXPECTED_CTC = _env("EXPECTED_CTC", "33")

STATE_FILE = BASE_DIR / "applied_jobs.json"
ARCHIVE_FILE = BASE_DIR / "applied_jobs.archive.json"
RETENTION_DAYS = int(_env("RETENTION_DAYS", "60"))
FAILED_RETENTION_DAYS = int(_env("FAILED_RETENTION_DAYS", "14"))
SHOTS_DIR = BASE_DIR / "screenshots"
APPLIED_SHOTS_DIR = SHOTS_DIR / "applied"
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE = LOGS_DIR / "daily_apply.log"

try:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

handlers = [logging.StreamHandler(sys.stdout)]
try:
    handlers.append(logging.FileHandler(str(LOG_FILE), mode="w", encoding="utf-8"))
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=handlers)
log = logging.getLogger("NaukriDailyApply")


def clean_artifacts():
    """Cleans all screenshots, old logs, temporary files, and stale browser cache on every run."""
    cleaned_items = []

    # 1. Screenshots folder (all previous run screenshots)
    try:
        shot_count = 0
        if SHOTS_DIR.exists():
            for p in SHOTS_DIR.rglob("*"):
                if p.is_file():
                    try:
                        p.unlink()
                        shot_count += 1
                    except Exception:
                        pass
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        APPLIED_SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        if shot_count > 0:
            cleaned_items.append(f"{shot_count} screenshots")
    except Exception as e:
        log.warning(f"Could not clean screenshots folder: {e}")

    # 2. Logs folder & stray root log files
    try:
        log_count = 0
        if LOGS_DIR.exists():
            for p in LOGS_DIR.glob("*"):
                if p.is_file() and p.name != LOG_FILE.name:
                    try:
                        p.unlink()
                        log_count += 1
                    except Exception:
                        pass
        for p in BASE_DIR.glob("*.log"):
            if p != LOG_FILE:
                try:
                    p.unlink()
                    log_count += 1
                except Exception:
                    pass
        if log_count > 0:
            cleaned_items.append(f"{log_count} old log files")
    except Exception as e:
        log.warning(f"Could not clean logs: {e}")

    # 3. Temporary files (*.tmp, *.bak, *.corrupt.json, failed_*.png)
    try:
        tmp_count = 0
        for pattern in ("*.tmp", "*.bak", "applied_jobs.corrupt.json", "failed_*.png"):
            for p in BASE_DIR.glob(pattern):
                try:
                    p.unlink()
                    tmp_count += 1
                except Exception:
                    pass
        if tmp_count > 0:
            cleaned_items.append(f"{tmp_count} temporary files")
    except Exception as e:
        log.warning(f"Could not clean temporary files: {e}")

    # 4. Edge browser stale cache & crash dumps (safe: keeps login cookies & profile settings)
    try:
        profile_dir = BASE_DIR / "edge_naukri_profile"
        edge_cache_dirs = [
            profile_dir / "Crashpad" / "reports",
            profile_dir / "Default" / "Cache" / "Cache_Data",
            profile_dir / "Default" / "Code Cache" / "js",
            profile_dir / "Default" / "Code Cache" / "wasm",
            profile_dir / "Default" / "GPUCache",
            profile_dir / "ShaderCache",
            profile_dir / "GrShaderCache",
            profile_dir / "GPUPersistentCache",
        ]
        edge_cleaned = 0
        for cdir in edge_cache_dirs:
            if cdir.exists():
                for p in cdir.glob("*"):
                    if p.is_file():
                        try:
                            p.unlink()
                            edge_cleaned += 1
                        except Exception:
                            pass
        if edge_cleaned > 0:
            cleaned_items.append(f"{edge_cleaned} browser cache/crash dumps")
    except Exception as e:
        log.debug(f"Edge cache cleanup: {e}")

    # 5. Stale Python bytecode cache (__pycache__)
    try:
        pycache_dir = BASE_DIR / "__pycache__"
        if pycache_dir.exists():
            shutil.rmtree(pycache_dir, ignore_errors=True)
            cleaned_items.append("Python bytecode cache (__pycache__)")
    except Exception:
        pass

    # 6. Windows temporary Chromium/Edge session directories (%TEMP%/scoped_dir*)
    try:
        temp_dir = Path(os.environ.get("TEMP", ""))
        if temp_dir.exists():
            scoped_count = 0
            for p in temp_dir.glob("scoped_dir*"):
                try:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                        scoped_count += 1
                except Exception:
                    pass
            if scoped_count > 0:
                cleaned_items.append(f"{scoped_count} session temp folders")
    except Exception:
        pass

    # 7. Force Python Garbage Collector
    try:
        gc.collect()
    except Exception:
        pass

    if cleaned_items:
        log.info(f"Workspace cleanup: Removed {', '.join(cleaned_items)}.")
    else:
        log.info("Workspace cleanup: All folders are clean.")


clean_screenshots = clean_artifacts


# --------------------------------------------------------------------------- state
def prune_and_archive_state(state: dict) -> dict:
    """Auto-archives records older than RETENTION_DAYS (60d) and prunes failed attempts older than FAILED_RETENTION_DAYS (14d)."""
    jobs = state.get("jobs", {})
    if not jobs:
        return state

    today_dt = date.today()
    active_jobs = {}
    to_archive = {}
    pruned_failed = 0

    for jid, entry in jobs.items():
        job_date_str = entry.get("date", "")
        entry_status = entry.get("status", "")

        entry_date = None
        if job_date_str:
            try:
                entry_date = date.fromisoformat(job_date_str)
            except Exception:
                pass

        if not entry_date:
            active_jobs[jid] = entry
            continue

        age_days = (today_dt - entry_date).days

        # 1. Prune failed attempts older than FAILED_RETENTION_DAYS (14 days)
        if entry_status in ("failed", "skipped") and age_days > FAILED_RETENTION_DAYS:
            pruned_failed += 1
            continue

        # 2. Archive successful / already_applied jobs older than RETENTION_DAYS (60 days)
        if age_days > RETENTION_DAYS:
            to_archive[jid] = entry
        else:
            active_jobs[jid] = entry

    if to_archive:
        archive_data = {"jobs": {}}
        if ARCHIVE_FILE.exists():
            try:
                archive_data = json.loads(ARCHIVE_FILE.read_text(encoding="utf-8"))
                if "jobs" not in archive_data:
                    archive_data["jobs"] = {}
            except Exception:
                archive_data = {"jobs": {}}

        archive_data["jobs"].update(to_archive)
        tmp_archive = ARCHIVE_FILE.with_suffix(".tmp")
        tmp_archive.write_text(json.dumps(archive_data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_archive.replace(ARCHIVE_FILE)
        log.info(f"Auto-archived {len(to_archive)} jobs older than {RETENTION_DAYS} days to {ARCHIVE_FILE.name}.")

    if pruned_failed > 0:
        log.info(f"Pruned {pruned_failed} stale failed attempts older than {FAILED_RETENTION_DAYS} days.")

    if len(active_jobs) != len(jobs):
        state["jobs"] = active_jobs
        save_state(state)
        log.info(f"Active state file optimized: {len(active_jobs)} active records retained.")

    return state


def load_state() -> dict:
    """State = {"jobs": {job_id: {title, company, status, note, date, at}}}."""
    if not STATE_FILE.exists():
        return {"jobs": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        shutil.copy(STATE_FILE, BASE_DIR / "applied_jobs.corrupt.json")
        log.warning("applied_jobs.json was unreadable; backed it up and started fresh.")
        return {"jobs": {}}
    if "jobs" not in data:
        shutil.copy(STATE_FILE, BASE_DIR / "applied_jobs.legacy.json")
        log.info("Old-format history backed up to applied_jobs.legacy.json; starting an ID-based history.")
        return {"jobs": {}}
    return prune_and_archive_state(data)


def save_state(state: dict):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def applied_today(state: dict) -> int:
    today = date.today().isoformat()
    unique_apps = set()
    for k, j in state.get("jobs", {}).items():
        if j.get("status") == "applied" and j.get("date") == today:
            unique_apps.add(j.get("at") or k)
    return len(unique_apps)


def record(state: dict, job: dict, status: str, note: str = ""):
    entry = {
        "title": job["title"], "company": job["company"], "status": status, "note": note,
        "date": date.today().isoformat(), "at": datetime.now().isoformat(timespec="seconds"),
    }
    state["jobs"][job["id"]] = entry
    if job.get("card_id") and job["card_id"] != job["id"]:
        state["jobs"][job["card_id"]] = entry
    save_state(state)


# --------------------------------------------------------------------------- parsing helpers
JOB_ID_RE = re.compile(r"-(\d{8,})(?:[/?#]|$)")
AGE_DAYS_RE = re.compile(r"(\d+)\s*\+?\s*d(?:ays?)?\s*ago", re.I)
AGE_RECENT_RE = re.compile(r"just now|today|\bhrs?\b|hours?|few\s+(?:hours|minutes)|\bmins?\b", re.I)


def job_id_from_url(url: str) -> str:
    m = JOB_ID_RE.search(url or "")
    return m.group(1) if m else ""


def parse_age_days(text: str):
    """'1d ago' -> 1, '32 hrs' -> 0, 'Just now' -> 0, unknown -> None."""
    m = AGE_DAYS_RE.search(text or "")
    if m:
        return int(m.group(1))
    if AGE_RECENT_RE.search(text or ""):
        return 0
    return None


def slug(text: str, n=40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:n] or "job"


def answer_for(text: str, options: list = None) -> str:
    q = (text or "").lower()
    opts_clean = []
    for o in (options or []):
        for line in o.split("\n"):
            line = line.strip()
            if line and line not in opts_clean and len(line) < 60:
                opts_clean.append(line)

    def match_option(targets, fallback=None):
        if not opts_clean:
            return fallback
        # 1. Exact case-insensitive match
        for t in targets:
            t_low = t.strip().lower()
            for o in opts_clean:
                if t_low == o.strip().lower():
                    return o
        # 2. Whole word boundary match
        for t in targets:
            t_low = t.strip().lower()
            pattern = r"\b" + re.escape(t_low) + r"\b"
            for o in opts_clean:
                if re.search(pattern, o.strip().lower()):
                    return o
        # 3. Substring match (target inside option)
        for t in targets:
            t_low = t.strip().lower()
            if len(t_low) >= 3:
                for o in opts_clean:
                    if t_low in o.strip().lower():
                        return o
        return fallback or opts_clean[0]

    # --- 1. NEGATIVE DISQUALIFIERS (Must ALWAYS answer NO / None / Decline) ---
    # Visa Sponsorship required?
    if re.search(r"require\s*(visa|sponsorship|work\s*visa)|need\s*(visa|sponsorship)|visa sponsorship", q):
        return match_option(["no", "not required", "don't require", "do not require", "i am an indian citizen"], "No")
    # Criminal record / legal convictions
    if re.search(r"criminal|convict|conviction|court\s*case|felony|police", q):
        return match_option(["no", "none", "never", "not have"], "No")
    # Military / Veteran
    if re.search(r"military|spouse|veteran|armed forces", q):
        return match_option(["not a military", "i am not", "no", "choose not to disclose", "prefer not to disclose", "decline"], "No")
    # Disability / Diversity
    if re.search(r"disability|handicap|pwd|specially abled", q):
        return match_option(["no", "none", "i do not have", "choose not to disclose", "prefer not to disclose", "decline"], "No")
    # Career gap / breaks
    if re.search(r"gap|break in career|career break|employment gap|education gap", q):
        return match_option(["no", "none", "0", "do not have", "no gap", "zero", "n/a"], "No")
    # Offers in hand
    if re.search(r"\boffer\b|offers in hand|any counter offer", q):
        return match_option(["no", "none", "0", "do not have"], "No")
    # Bond / Service agreement with previous employer
    if re.search(r"\bbond\b|service agreement|non-compete|obligation", q):
        return match_option(["no", "none", "not applicable", "na"], "No")

    # --- 2. POSITIVE ENABLERS (Must ALWAYS answer YES / Affirmative) ---
    # Work authorization in India
    if re.search(r"authorized to work in india|legally authorized|work permit in india|indian citizen|right to work", q):
        return match_option(["yes", "authorized", "indian citizen", "citizen"], "Yes")
    # Passport availability
    if re.search(r"valid passport|do you have.*passport|passport available", q):
        return match_option(["yes", "i have", "available"], "Yes")
    # Ready to relocate
    if re.search(r"relocate|relocation|open to relocate|willing to relocate", q):
        return match_option(["yes", "bengaluru", "bangalore", "open", "flexible"], "Yes")
    # Shifts / Hours / Rotational / Night / Weekend / Overtime
    if re.search(r"shift|rotational|night shift|work hours|flexible hours|overtime|weekend|travel", q):
        return match_option(["yes", "agree", "comfortable", "flexible", "open"], "Yes")
    # Work mode (Hybrid / Remote / Onsite / Office)
    if re.search(r"hybrid|remote|wfh|onsite|work from office|in-office", q):
        return match_option(["yes", "comfortable", "agree", "flexible", "hybrid", "onsite"], "Yes")
    # Interview availability (F2F, Virtual, In-person, Immediate)
    if re.search(r"interview|f2f|in-person|face to face|virtual|walk-in|available for", q):
        return match_option(["yes", "available", "agree", "immediately"], "Yes")
    # Notice period negotiable / buyout
    if re.search(r"negotiable|buyout|can you reduce|serving notice|early join|serve notice", q):
        return match_option(["yes", "serving", "negotiable", "buyout possible"], "Yes")

    # --- 3. CANDIDATE CONTACT & PERSONAL DETAILS (from Resume) ---
    if re.search(r"\bfirst\s*name\b", q):
        return CANDIDATE_FIRST_NAME
    if re.search(r"\blast\s*name\b|\bsurname\b", q):
        return CANDIDATE_LAST_NAME
    if re.search(r"candidate name|full\s*name|your name|applicant name", q):
        return CANDIDATE_NAME
    if re.search(r"phone|mobile|contact number|cell|calling number|whatsapp", q):
        return CANDIDATE_PHONE
    if re.search(r"email|mail\s*id|email\s*address", q):
        return CANDIDATE_EMAIL
    if re.search(r"linkedin|profile link|social url", q):
        return LINKEDIN_URL
    if re.search(r"github|portfolio|repo", q):
        return GITHUB_URL
    if re.search(r"\bgender\b|\bsex\b", q):
        return match_option(["female", "f"], "Female")
    if re.search(r"marital|married|single", q):
        return match_option(["single", "unmarried", "prefer not to disclose"], "Single")
    if re.search(r"nationality|citizenship|citizen", q):
        return match_option(["indian", "india"], "Indian")
    if re.search(r"\bpan\b|permanent account number", q):
        if opts_clean and any(o.lower() in ("yes", "y") or o.lower().startswith("yes") for o in opts_clean):
            return "Yes"
        return PAN_NUMBER

    # --- 4. LOCATION (Bangalore / Bengaluru) ---
    if re.search(r"location|city|residing|preferred location|current location|where are you|based out of|base location|work location|residence|place|state|hometown", q):
        if opts_clean:
            for pref in ["bengaluru", "bangalore", "blr", "karnataka"]:
                for o in opts_clean:
                    if pref in o.lower():
                        return o
            for o in opts_clean:
                if o.lower() in ("yes", "y") or o.lower().startswith("yes"):
                    return o
            for o in opts_clean:
                if "any" in o.lower() or "other" in o.lower():
                    return o
            return opts_clean[0]
        return PREFERRED_LOCATION or "Bengaluru"

    # --- 5. CURRENT & PREVIOUS EMPLOYMENT (from Resume) ---
    if re.search(r"previous company|past employer|previous employer|former company|previous organization|ex-employer|prior company|past company", q):
        return match_option(["capgemini", "tech mahindra"], PREVIOUS_COMPANY)
    if re.search(r"current company|present company|current employer|present employer|current organization|firm|working at|current workplace", q):
        return match_option(["dell", "dell technologies"], CURRENT_COMPANY)
    if re.search(r"current designation|present designation|current role|present role|current title|designation|job title", q):
        return match_option(["software senior engineer", "senior engineer", "sdet", "qa automation engineer", "lead"], CURRENT_DESIGNATION)
    if re.search(r"previous designation|previous role|past role", q):
        return match_option(["consultant", "engineer", "manager"], PREVIOUS_DESIGNATION)
    if re.search(r"client|client project", q):
        return match_option(["asml", "rakuten"], "ASML / Rakuten")

    # --- 6. EDUCATION & ACADEMICS (from Resume) ---
    if re.search(r"year of passing|passing year|graduation year|year of graduation|completion year|batch", q):
        return match_option(["2020", "2016-2020"], GRADUATION_YEAR)
    if re.search(r"percentage|marks|cgpa|grade|gpa|percent", q):
        return match_option(["87%", "85-90", "80-90", "8.7", "87", "above 80"], GRADUATION_PERCENTAGE)
    if re.search(r"stream|branch|specialization|discipline|field of study|major", q):
        return match_option(["electronics", "ece", "electronics & communication", "engineering"], EDUCATION_STREAM)
    if re.search(r"degree|qualification|graduation|highest education|course", q):
        return match_option(["b.tech", "btech", "b.e", "be", "bachelor", "engineering", "graduate"], EDUCATION_DEGREE)
    if re.search(r"college|university|institute|campus|school", q):
        return match_option(["bapatla", "bapatla college of engineering"], COLLEGE_NAME)
    if re.search(r"education type|course type|mode of education|full time|part time", q):
        return match_option(["full time", "regular", "full-time"], "Full Time")

    # --- 7. NOTICE PERIOD & JOINING TIMELINE ---
    if re.search(r"notice|joining|join|last working|available|timeline|how soon", q):
        if opts_clean:
            for pref in ["immediate joiner", "immediate", "immediately", "available now", "available", "serving", "15 days", "30 days", "1 month"]:
                for o in opts_clean:
                    if pref in o.lower():
                        return o
            def extract_min_num(opt_str):
                nums = re.findall(r"\d+", opt_str)
                return min(int(n) for n in nums) if nums else 9999
            opts_with_nums = [(extract_min_num(o), o) for o in opts_clean]
            opts_with_nums.sort(key=lambda x: x[0])
            if opts_with_nums and opts_with_nums[0][0] != 9999:
                return opts_with_nums[0][1]
            return opts_clean[0]
        if re.search(r"how many days|in days|number of days", q):
            return "0"
        return "Immediate joiner"

    # --- 8. CTC & COMPENSATION ---
    if re.search(r"ctc|salary|lpa|lakh|compensation", q):
        val = CURRENT_CTC if "current" in q or "present" in q or "fixed" in q else EXPECTED_CTC
        if opts_clean:
            for o in opts_clean:
                if val in o:
                    return o
            for pref in ["30", "33", "25-35", "30+", "25+", "20-30", "30-40", "28-35"]:
                for o in opts_clean:
                    if pref in o:
                        return o
            return opts_clean[-1]
        return val

    # --- 9. NARRATIVE / OPEN-ENDED QUESTIONS ---
    if re.search(r"summary|responsibilit|about your|project|profile|describe|brief|overview|achievement|introduction|tell me about", q):
        return "Software Senior Engineer with 6+ years of experience specializing in SDET Automation, UI & REST API test automation frameworks using Python, Java, Selenium, REST Assured, and CI/CD."
    if re.search(r"reason for|why.*change|why.*leaving|why.*switch|why do you want", q):
        return "Seeking career growth and impactful opportunities in automation engineering."

    # --- 10. SKILL-SPECIFIC EXPERIENCE & RATINGS ---
    if re.search(r"rate\s*your|rating|rate\s*yourself|scale of\s*1\s*to\s*5|scale of\s*1\s*to\s*10", q):
        if "10" in q:
            return match_option(["9", "10", "8", "expert"], "9")
        return match_option(["5", "4", "expert", "advanced"], "5")

    skill_exp_map = {
        "python": "6",
        "selenium": "6",
        "selenide": "5",
        "api": "6",
        "rest": "5",
        "java": "5",
        "robot": "4",
        "appium": "3",
        "mobile": "3",
        "jenkins": "5",
        "git": "6",
        "ci": "5",
        "pytest": "5",
        "junit": "5",
        "sql": "4",
        "bdd": "4",
    }
    for skill_key, yrs in skill_exp_map.items():
        if skill_key in q:
            if re.search(r"experience|years|yrs|\bexp\b", q):
                if opts_clean:
                    for pref in [yrs, f"{yrs}+", "5-8", "4-6", "3-6", f"{yrs} years"]:
                        for o in opts_clean:
                            if pref in o.lower():
                                return o
                    return opts_clean[len(opts_clean) // 2]
                return yrs
            elif "yes/no" in q or re.search(r"^(do|have|are|did|can)\b", q.strip()):
                return match_option(["yes", "expert", "proficient"], "Yes")

    if re.search(r"experience|years|yrs|\bexp\b", q):
        if opts_clean:
            for pref in ["6", "5-8", "5 to 8", "6+", "6-8", "5-7", "5+", "4-6", "3-6", "5-10", "4-8", "5", "4", "7", "8"]:
                for o in opts_clean:
                    if pref in o.lower():
                        return o
            return opts_clean[len(opts_clean) // 2]
        return EXPERIENCE_YEARS

    if re.search(r"top\s*\d*\s*skills|key skills|primary skills|technical skills|skills", q):
        return SKILLS


    # --- 11. GENERAL YES/NO QUESTIONS ---
    if opts_clean:
        for o in opts_clean:
            if o.lower() in ("yes", "y") or o.lower().startswith("yes"):
                return o
    if not re.search(r"how many|how much", q):
        if "yes/no" in q or re.search(r"^(are|is|do|does|did|have|has|can|could|will|would|were|willing|comfortable|open)\b", q.strip()):
            return "Yes"

    # --- 12. UNIVERSAL FALLBACK ---
    if opts_clean:
        for pref in ["yes", "agree", "confirm", "available", "positive", "immediate", "all of the above"]:
            for o in opts_clean:
                if pref in o.lower():
                    return o
        positives = [o for o in opts_clean if not any(neg in o.lower() for neg in ["not eligible", "cannot", "none", "disqualif", "no "])]
        if positives:
            return positives[0]
        return opts_clean[0]

    return "Yes"




# --------------------------------------------------------------------------- browser
def get_driver():
    is_headless = HEADLESS
    target_browser = BROWSER

    log.info(f"Initializing browser: {target_browser.upper()} (Headless: {is_headless})")

    if target_browser == "chrome":
        profile_dir = BASE_DIR / "chrome_naukri_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        opts = ChromeOptions()
        opts.add_argument(f"--user-data-dir={profile_dir}")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--remote-debugging-pipe")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        if is_headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
        else:
            opts.add_argument("--start-maximized")
            opts.add_argument("--window-size=1842,956")

        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=opts)
        except Exception:
            driver = webdriver.Chrome(options=opts)
    else:
        profile_dir = BASE_DIR / "edge_naukri_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        opts = EdgeOptions()
        opts.add_argument(f"--user-data-dir={profile_dir}")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-software-rasterizer")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        if is_headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0")
        else:
            opts.add_argument("--start-maximized")
            opts.add_argument("--window-size=1842,956")

        try:
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
            driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=opts)
        except Exception as e:
            if sys.platform == "win32" and ("Chrome instance exited" in str(e) or "session not created" in str(e).lower()):
                log.warning("Edge profile was locked by an existing process. Closing stale Edge processes and retrying...")
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "msedgedriver.exe"], capture_output=True)
                subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
                time.sleep(2)
                try:
                    from webdriver_manager.microsoft import EdgeChromiumDriverManager
                    driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=opts)
                except Exception:
                    driver = webdriver.Edge(options=opts)
            else:
                driver = webdriver.Edge(options=opts)

    driver.set_page_load_timeout(35)
    driver.set_script_timeout(25)

    if sys.platform == "win32" and not is_headless:
        try:
            import ctypes
            import win32gui
            import win32con
            user32 = ctypes.windll.user32
            driver.maximize_window()
            time.sleep(1)

            def bring_to_front():
                def callback(hwnd, extra):
                    if win32gui.IsWindowVisible(hwnd):
                        text = win32gui.GetWindowText(hwnd).lower()
                        if "edge" in text or "chrome" in text or "naukri" in text:
                            try:
                                user32.AllowSetForegroundWindow(-1)
                            except Exception:
                                pass
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                            win32gui.BringWindowToTop(hwnd)
                            win32gui.SetForegroundWindow(hwnd)
                    return True
                win32gui.EnumWindows(callback, None)

            bring_to_front()
        except Exception as e:
            log.debug(f"Window foreground adjust: {e}")

    return driver


def visible(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def click(driver, el):
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)


def snap(driver, name: str):
    try:
        SHOTS_DIR.mkdir(exist_ok=True)
        driver.save_screenshot(str(SHOTS_DIR / f"{name}.png"))
    except Exception:
        pass


def dismiss_popups(driver):
    try:
        if driver.find_elements(By.XPATH, "//*[normalize-space(text())='Add Custom Application']"):
            for b in driver.find_elements(By.XPATH, "//button[normalize-space(.)='Cancel']"):
                if visible(b):
                    click(driver, b)
                    time.sleep(1)
                    return
    except WebDriverException:
        pass


# --------------------------------------------------------------------------- cookies & login
def load_cookies(driver, cookies_file=None, cookies_env=""):
    """Loads saved session cookies into the browser to bypass login/OTP."""
    cookies = []
    env_val = cookies_env or NAUKRI_COOKIES
    file_path = cookies_file or COOKIES_FILE

    if env_val:
        try:
            cookies = json.loads(env_val)
        except Exception:
            pass
    elif file_path and Path(file_path).exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
        except Exception:
            pass

    if cookies:
        log.info(f"Injecting {len(cookies)} saved session cookies...")
        try:
            driver.get("https://www.naukri.com")
            time.sleep(2)
            for c in cookies:
                c.pop("sameSite", None)
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
            log.info("Session cookies injected successfully.")
        except Exception as e:
            log.warning(f"Could not inject cookies: {e}")


def save_cookies(driver, cookies_file=None):
    """Saves active session cookies to disk."""
    target_file = cookies_file or COOKIES_FILE
    try:
        cookies = driver.get_cookies()
        if cookies:
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            log.info(f"Session cookies saved to {Path(target_file).name}.")
    except Exception as e:
        log.warning(f"Could not save cookies: {e}")


def _looks_logged_in(driver) -> bool:
    url = driver.current_url.lower()
    if "nlogin" in url or "login" in url:
        return False
    return bool(driver.find_elements(
        By.CSS_SELECTOR, "a[href*='mnjuser/profile'], .nI-gNb-drawer__bars, .view-profile-wrapper"))


def check_is_logged_in(driver) -> bool:
    driver.get("https://www.naukri.com/mnjuser/homepage")
    time.sleep(3)
    return _looks_logged_in(driver)


def ensure_login(driver) -> bool:
    # 1. Try saved cookies first
    load_cookies(driver)
    if check_is_logged_in(driver):
        log.info("Already logged in (via saved session/cookies).")
        save_cookies(driver)
        return True

    # 2. Check credentials
    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        log.error("Not logged in and NAUKRI_EMAIL / NAUKRI_PASSWORD not provided.")
        return False

    log.info("Logging in with credentials...")
    driver.get("https://www.naukri.com/nlogin/login")
    try:
        wait = WebDriverWait(driver, 15)
        user = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@id='usernameField'] | //input[contains(@placeholder,'Email')]")))
        pwd = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@id='passwordField'] | //input[@type='password']")))
        user.clear(); user.send_keys(NAUKRI_EMAIL)
        pwd.clear(); pwd.send_keys(NAUKRI_PASSWORD)
        click(driver, driver.find_element(By.XPATH, "//button[@type='submit' or contains(.,'Login')]"))
    except Exception as e:
        log.error(f"Login form problem: {e}")

    wait_limit = MANUAL_LOGIN_WAIT if not HEADLESS else min(MANUAL_LOGIN_WAIT, 30)
    deadline = time.time() + wait_limit
    warned = False
    while time.time() < deadline:
        time.sleep(4)
        if _looks_logged_in(driver):
            log.info("Login confirmed.")
            save_cookies(driver)
            return True
        if not warned and not HEADLESS:
            log.warning(f"Not logged in yet. If a CAPTCHA/OTP is showing, complete it in the browser "
                        f"(waiting up to {wait_limit}s).")
            warned = True

    if HEADLESS:
        log.error("Headless login could not be confirmed automatically. Tip: Save cookies to cookies.json or set NAUKRI_COOKIES secret to bypass OTP/CAPTCHA.")
    else:
        log.error("Login could not be confirmed. Stopping so nothing is applied while logged out.")
    return False


# --------------------------------------------------------------------------- search + cards
def build_url(query: str, page: int, age_days: int, location: str) -> str:
    path = f"{query.lower().replace(' ', '-')}-jobs"
    if location:
        path += f"-in-{location.lower().replace(' ', '-')}"
    if page > 1:
        path += f"-{page}"
    url = f"https://www.naukri.com/{path}?k={quote(query)}"
    if location:
        url += f"&l={quote(location)}"
    return url + f"&jobAge={age_days}"


def search_plan():
    ages = sorted(AGE_WINDOWS)
    plan = []
    if LOCATION:
        near, late = ages[:3], ages[3:]
        plan += [(LOCATION, a) for a in near]
        if ANYWHERE_FALLBACK:
            plan += [("", a) for a in near]
        for a in late:
            plan.append((LOCATION, a))
            if ANYWHERE_FALLBACK:
                plan.append(("", a))
    else:
        for a in ages:
            plan.append(("", a))
    return plan


def load_cards(driver, url: str) -> list:
    """Open a search page and return every job card that has a 'Quick apply' button."""
    try:
        driver.get(url)
        time.sleep(5)
        dismiss_popups(driver)
        for _ in range(4):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(0.8)
    except Exception as e:
        log.warning(f"Warning loading search page ({e})")
        if any(term in str(e).lower() for term in ("crashed", "disconnected", "session not created", "no such window", "invalid session", "timed out", "timeout")):
            raise
        return []
    cards, seen = [], set()
    buttons = driver.find_elements(
        By.XPATH, "//*[normalize-space(text())='Quick apply' or normalize-space(text())='Quick Apply']")
    for idx, btn in enumerate(buttons):
        try:
            # 1. Classic layout check
            card, link = btn, None
            for _ in range(8):
                card = card.find_element(By.XPATH, "..")
                found = card.find_elements(By.XPATH, ".//a[contains(@href,'job-listings')]")
                if found:
                    link = found[0]
                    break

            if link is not None:
                href = link.get_attribute("href") or ""
                job_id = card.get_attribute("data-job-id") or job_id_from_url(href)
                title = (link.get_attribute("title") or link.text or "").strip() or f"job {job_id}"
                comp = ""
                for c in card.find_elements(By.XPATH, ".//a[contains(@class,'comp')]"):
                    if c.text.strip():
                        comp = c.text.strip()
                        break
            else:
                # 2. Modern Naukri / TopTier layout
                try:
                    card = btn.find_element(By.XPATH, "ancestor::*[contains(@class, 'cursor-pointer')][1]")
                except Exception:
                    card = btn.find_element(By.XPATH, "../../../..")
                href = ""
                h4s = card.find_elements(By.TAG_NAME, "h4")
                lines = [l.strip() for l in card.text.split("\n") if l.strip()]
                title = ""
                for l in lines:
                    if any(k in l.lower() for k in ["engineer", "developer", "tester", "qa", "python", "automation", "lead", "architect", "sdet", "consultant"]):
                        title = l
                        break
                if not title and h4s:
                    title = h4s[0].text.strip()
                if not title and len(lines) > 5:
                    title = lines[5]
                title = title or f"job_{idx}"
                comp = lines[0] if lines else ""
                job_id = card.get_attribute("data-job-id") or f"card_{idx}_{slug(title)}"

            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            cards.append({"id": job_id, "title": title, "company": comp, "url": href,
                          "age": parse_age_days(card.text), "button": btn})
        except Exception:
            continue
    log.info(f"  {len(cards)} Quick-apply cards on page.")
    return cards


# --------------------------------------------------------------------------- job page: the bottom button
CTA_JS = """
const re = /^(quick apply|applied\\s*[\\u2713\\u2714]?)$/i;
const all = Array.from(document.querySelectorAll('button, a, div, span'));
for (const el of all.reverse()) {
  const t = (el.innerText || '').trim();
  if (!re.test(t)) continue;
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) continue;
  let n = el, pinned = false;
  for (let i = 0; i < 6 && n; i++) {
    const p = getComputedStyle(n).position;
    if (p === 'fixed' || p === 'sticky') { pinned = true; break; }
    n = n.parentElement;
  }
  if (pinned) {
    const target = el.closest('button, a') || el;
    return [target, t];
  }
}
return null;
"""
QA_TEXT = "normalize-space(text())='Quick apply' or normalize-space(text())='Quick Apply'"


def pinned_cta(driver):
    try:
        return driver.execute_script(CTA_JS)
    except WebDriverException:
        return None


def on_job_page(driver) -> bool:
    return "job-listings" in driver.current_url.lower()


IS_APPLIED_JS = """
// If questionnaire drawer is currently open and has active questions, NOT applied yet!
const drawer = document.querySelector('.chatbot_DrawerContentWrapper, .chatbot_MessageContainer');
if (drawer && drawer.offsetParent !== null) {
    const text = (drawer.innerText || '').toLowerCase();
    const isCompleted = text.includes('thanks for the response') || 
                        text.includes('thank you for applying') || 
                        text.includes('application has been submitted') ||
                        text.includes('thanks for your response') ||
                        text.includes('thank you for your response') ||
                        text.includes('thanks for your responses') ||
                        text.includes('thank you for your responses') ||
                        text.includes('thank you for response') ||
                        text.includes('thank you for responses') ||
                        text.includes('responses have been recorded') ||
                        text.includes('responses recorded') ||
                        text.includes('response recorded') ||
                        text.includes('thanks for submitting');
    if (!isCompleted) {
        return false;
    }
}

// 1. Modern TopTier check
const container = document.querySelector('.z-jobCardApply');
if (container) {
    const btn = container.querySelector('button');
    if (btn) {
        if (btn.classList.contains('bg-i100') || container.querySelector('.bg-i100') || btn.classList.contains('!border-i100')) {
            return true;
        }
        for (const s of btn.querySelectorAll('span')) {
            const txt = (s.innerText || s.textContent || '').trim().toLowerCase();
            if (txt === 'applied') {
                const cls = (s.className || '') + ' ' + ((s.parentElement && s.parentElement.className) || '');
                if (cls.includes('translate-y-0') && !cls.includes('translate-y-full')) return true;
            }
        }
        const btxt = (btn.innerText || '').trim().toLowerCase();
        if (btxt === 'applied' || btxt.startsWith('applied')) {
            return true;
        }
        return false;
    }
}
// 2. Classic layout check
for (const b of document.querySelectorAll('button, a')) {
    const t = (b.innerText || '').trim().toLowerCase();
    if (t === 'applied' || t.startsWith('applied ✓') || (t.startsWith('applied') && !t.includes('quick'))) {
        return true;
    }
}
return false;
"""


def is_applied(driver) -> bool:
    """True ONLY when the job page shows green 'Applied ✓'."""
    if not on_job_page(driver):
        return False
    try:
        return bool(driver.execute_script(IS_APPLIED_JS))
    except WebDriverException:
        return False


def click_apply_button(driver) -> bool:
    # 1. Modern TopTier layout (.z-jobCardApply button)
    container = driver.find_elements(By.CSS_SELECTOR, ".z-jobCardApply")
    if container:
        btns = container[0].find_elements(By.TAG_NAME, "button")
        if btns:
            btn = btns[0]
            log.info("    Job page: clicking bottom '.z-jobCardApply' button")
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(1)
                ActionChains(driver).move_to_element(btn).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            return True

    # 2. Classic layout check
    r = pinned_cta(driver)
    if r and "quick apply" in r[1].lower():
        log.info("    Job page: clicking pinned CTA")
        btn = r[0]
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(1)
            ActionChains(driver).move_to_element(btn).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        return True

    # 3. XPath fallback
    cands = driver.find_elements(By.XPATH, f"//h1/ancestor::*[.//*[{QA_TEXT}]][1]//*[{QA_TEXT}]")
    for el in cands:
        if visible(el):
            log.info("    Job page: clicking header 'Quick apply' (fallback)")
            target = el.find_element(By.XPATH, "ancestor-or-self::button | ancestor-or-self::a") if el.tag_name not in ('button', 'a') else el
            click(driver, target)
            return True
    return False


def snap_applied(driver, job: dict) -> str:
    """Screenshot of the job page showing the green 'Applied ✓' button."""
    APPLIED_SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = APPLIED_SHOTS_DIR / f"{date.today().isoformat()}_{datetime.now():%H%M%S}_{job['id']}_{slug(job['title'])}.png"
    try:
        driver.save_screenshot(str(path))
    except Exception as e:
        log.warning(f"Could not save screenshot: {e}")
        return ""
    return str(path)


# --------------------------------------------------------------------------- the recruiter chatbot
CHAT_NOISE = {"save", "yes", "no", "skip this question", "type here...", "type message here...", "next"}


def find_chat_drawer(driver):
    """Finds modern Naukri TopTier chatbot drawer or classic chat box."""
    for d in driver.find_elements(By.CSS_SELECTOR, ".chatbot_DrawerContentWrapper, .chatbot_MessageContainer"):
        if d.is_displayed():
            return d
    for save in driver.find_elements(By.XPATH, "//button[normalize-space(.)='Save']"):
        if save.is_displayed():
            node = save
            for _ in range(8):
                node = node.find_element(By.XPATH, "..")
                if len((node.text or "").strip()) >= 20:
                    return node
    return None


def chat_step(driver, drawer, seen: dict) -> str:
    try:
        text = (drawer.text or "").strip()
        if any(w in text.lower() for w in [
            "thank you for your response",
            "thank you for your responses",
            "thanks for your responses",
            "thank you for response",
            "thank you for responses",
            "thanks for the response",
            "thanks for your response",
            "thank you for applying",
            "application has been submitted",
            "thanks for submitting",
            "responses have been recorded",
            "responses recorded",
            "response recorded",
            "successfully applied"
        ]):
            log.info("    Chatbot: response confirmed; waiting for drawer to close...")
            time.sleep(3)
            return "completed"

        # Check if bot is still loading the first question
        bot_msgs = drawer.find_elements(By.CSS_SELECTOR, ".botItem, .botMsg, [class*='botMsg']")
        q_lines = []
        for bm in bot_msgs:
            try:
                t = bm.text.strip()
                if t and "thank you for showing interest" not in t.lower() and "kindly answer all the recruiter" not in t.lower() and len(t) > 3:
                    q_lines.append(t)
            except Exception:
                pass

        if not q_lines:
            time.sleep(2)
            return "acted"

        current_q = q_lines[-1]
        seen[current_q] = seen.get(current_q, 0) + 1
        if seen[current_q] > 5:
            skips = drawer.find_elements(By.XPATH, ".//*[normalize-space(text())='Skip this question' or contains(text(), 'Skip')]")
            if skips:
                log.info("    Question repeating -> clicking Skip")
                driver.execute_script("arguments[0].click();", skips[0])
                time.sleep(2)
            return f"stuck:question keeps repeating: {current_q[:70]}"

        # 1. Check for options containers (radio or multi-checkbox)
        ssrc_containers = drawer.find_elements(By.CSS_SELECTOR, ".ssrc__radio-btn-container")
        mcc_containers = drawer.find_elements(By.CSS_SELECTOR, ".multicheckboxes-container label, .mcc__label")

        # 2. Check for input elements (contenteditable, text, number, textarea)
        inputs = drawer.find_elements(By.CSS_SELECTOR, ".textArea[contenteditable='true'], [contenteditable='true'], input[type='text'], input[type='number'], textarea")
        inputs = [i for i in inputs if i.is_displayed()]

        matched = False

        if ssrc_containers:
            options_text = []
            for c in ssrc_containers:
                t = (c.text or "").strip()
                if not t:
                    inps = c.find_elements(By.TAG_NAME, "input")
                    if inps:
                        t = (inps[0].get_attribute("value") or inps[0].get_attribute("id") or "").strip()
                if t and t not in options_text:
                    options_text.append(t)
            
            ans = answer_for(current_q, options_text)
            log.info(f"    Q: {current_q[-70:]!r} -> Radio Answer: {ans!r}")

            for c in ssrc_containers:
                t = (c.text or "").strip().lower()
                inp = c.find_elements(By.TAG_NAME, "input")
                inp_val = (inp[0].get_attribute("value") or inp[0].get_attribute("id") or "").strip().lower() if inp else ""
                if ans.lower() == t or ans.lower() in t or ans.lower() == inp_val or (len(ans) > 2 and ans.lower() in inp_val):
                    lbl = c.find_elements(By.TAG_NAME, "label")
                    target = lbl[0] if lbl else c
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
                    time.sleep(0.3)
                    try:
                        ActionChains(driver).move_to_element(target).click().perform()
                    except Exception:
                        pass
                    driver.execute_script("""
                        arguments[0].click();
                        const r = arguments[0].querySelector('input[type="radio"]') || 
                                  arguments[0].parentElement.querySelector('input[type="radio"]');
                        if (r) {
                            r.checked = true;
                            r.click();
                            r.dispatchEvent(new Event('change', { bubbles: true }));
                            r.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    """, target)
                    matched = True
                    break

            if not matched and ssrc_containers:
                log.info(f"    Radio fallback: auto-selecting best option: {ssrc_containers[0].text.strip()!r}")
                lbl = ssrc_containers[0].find_elements(By.TAG_NAME, "label")
                target = lbl[0] if lbl else ssrc_containers[0]
                driver.execute_script("""
                    arguments[0].click();
                    const r = arguments[0].querySelector('input[type="radio"]') || 
                              arguments[0].parentElement.querySelector('input[type="radio"]');
                    if (r) {
                        r.checked = true;
                        r.click();
                        r.dispatchEvent(new Event('change', { bubbles: true }));
                        r.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                """, target)
                matched = True

        elif mcc_containers:
            options_text = [m.text.strip() for m in mcc_containers if m.text.strip()]
            ans = answer_for(current_q, options_text)
            log.info(f"    Q: {current_q[-70:]!r} -> Checkbox Answer: {ans!r}")
            for m in mcc_containers:
                t = m.text.strip().lower()
                if ans.lower() == t or (len(ans) > 2 and ans.lower() in t) or (len(t) > 2 and t in ans.lower()):
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", m)
                    time.sleep(0.3)
                    driver.execute_script("""
                        const label = arguments[0];
                        const container = label.closest('li, div, .mcc__label-container') || label.parentElement;
                        const cb = container ? (container.querySelector('input[type="checkbox"]') || label.querySelector('input[type="checkbox"]')) : null;
                        if (cb) {
                            if (!cb.checked) {
                                cb.checked = true;
                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                cb.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        } else {
                            label.click();
                        }
                    """, m)
                    matched = True
                    break

            if not matched and mcc_containers:
                log.info(f"    Checkbox fallback: auto-selecting best option: {mcc_containers[0].text.strip()!r}")
                driver.execute_script("""
                    const label = arguments[0];
                    const container = label.closest('li, div, .mcc__label-container') || label.parentElement;
                    const cb = container ? (container.querySelector('input[type="checkbox"]') || label.querySelector('input[type="checkbox"]')) : null;
                    if (cb) {
                        if (!cb.checked) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                            cb.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    } else {
                        label.click();
                    }
                """, mcc_containers[0])
                matched = True

        # 3. If NO radio/checkbox, and an input box is present -> TYPE THE ANSWER
        if not matched and inputs:
            ans = answer_for(current_q, [])
            inp = inputs[-1]
            inp_type = (inp.get_attribute("type") or "").lower()
            if inp_type == "number":
                nums = re.findall(r"\d+(?:\.\d+)?", ans)
                if nums:
                    ans = nums[0]
            log.info(f"    Q: {current_q[-70:]!r} -> Input Text Answer: {ans!r}")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].focus();", inp)
            time.sleep(0.2)

            if inp.get_attribute("contenteditable") == "true":
                driver.execute_script("""
                    const el = arguments[0];
                    const val = String(arguments[1]);
                    el.focus();
                    el.innerText = '';
                    el.textContent = '';
                    el.innerHTML = '';
                    try {
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                        document.execCommand('insertText', false, val);
                    } catch(e) {}
                    if (el.innerText.trim() !== val) {
                        el.innerText = val;
                        el.textContent = val;
                    }
                    el.dispatchEvent(new Event('focus', { bubbles: true }));
                    el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: val }));
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: val }));
                    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: val }));
                    el.dispatchEvent(new KeyboardEvent('keypress', { bubbles: true, key: val }));
                    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: val }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));

                    const drawer = el.closest('.chatbot_DrawerContentWrapper') || document;
                    const sends = drawer.querySelectorAll('.send.disabled, [id^="sendMsg__"].disabled');
                    sends.forEach(s => s.classList.remove('disabled'));
                """, inp, ans)
            else:
                try:
                    inp.clear()
                except Exception:
                    pass
                inp.send_keys(ans)
            matched = True

        # 4. Fallback: only if NO input box exists, check for pill/button options attached to bot
        # (CRITICAL: exclude any element inside .userItem / .userMsg / .editable-listItem)
        if not matched:
            opt_els = drawer.find_elements(
                By.XPATH,
                ".//*[(self::button or contains(@class, 'chip') or contains(@class, 'option') or contains(@class, 'pills')) and "
                "not(contains(@class, 'chipMsg')) and "
                "not(ancestor-or-self::*[contains(@class, 'userItem') or contains(@class, 'userMsg') or contains(@class, 'editable-listItem') or contains(@class, 'chatbot_Nav')])]"
            )
            opt_els = [o for o in opt_els if o.is_displayed() and (o.text or "").strip() and o.text.strip().lower() not in CHAT_NOISE]
            if opt_els:
                options_text = [o.text.strip() for o in opt_els]
                ans = answer_for(current_q, options_text)
                log.info(f"    Q: {current_q[-70:]!r} -> Chip Answer: {ans!r}")
                for o in opt_els:
                    t = o.text.strip().lower()
                    if t == ans.lower() or (len(ans) > 2 and ans.lower() in t) or (len(t) > 2 and t in ans.lower()):
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", o)
                            time.sleep(0.3)
                            ActionChains(driver).move_to_element(o).click().perform()
                        except Exception:
                            pass
                        driver.execute_script("arguments[0].click();", o)
                        matched = True
                        break

                if not matched and opt_els:
                    log.info(f"    Chip fallback: auto-selecting best option: {opt_els[0].text.strip()!r}")
                    driver.execute_script("arguments[0].click();", opt_els[0])
                    matched = True

        if not matched:
            skips = drawer.find_elements(By.XPATH, ".//*[normalize-space(text())='Skip this question' or contains(text(), 'Skip')]")
            if skips:
                driver.execute_script("arguments[0].click();", skips[0])
                matched = True
            else:
                any_opts = drawer.find_elements(By.XPATH, ".//label | .//input[@type='radio'] | .//input[@type='checkbox']")
                if any_opts:
                    log.info("    Generic options fallback: selecting first available option")
                    driver.execute_script("arguments[0].click();", any_opts[0])
                    matched = True
                else:
                    if seen.get(current_q, 0) < 3:
                        time.sleep(1.5)
                        return "acted"
                    return f"stuck:no way to answer: {current_q[-80:]}"

        time.sleep(1)
        driver.execute_script("""
            const drawer = arguments[0];
            const disabledSends = document.querySelectorAll('.send.disabled, [id^="sendMsg__"].disabled, button.disabled');
            disabledSends.forEach(s => {
                s.classList.remove('disabled');
                s.removeAttribute('disabled');
            });
        """, drawer)

        save_clicked = False
        candidates = []
        try:
            candidates = drawer.find_elements(
                By.XPATH,
                ".//button[contains(translate(normalize-space(.), 'SAVE', 'save'), 'save')] | "
                ".//*[contains(@class, 'sendMsg') or contains(@class, 'send')] | "
                ".//button[contains(translate(normalize-space(.), 'SEND', 'send'), 'send')]"
            )
            if not candidates:
                candidates = driver.find_elements(
                    By.XPATH,
                    "//button[contains(translate(normalize-space(.), 'SAVE', 'save'), 'save')] | "
                    "//*[contains(@class, 'sendMsg') or contains(@class, 'send')] | "
                    "//button[contains(translate(normalize-space(.), 'SEND', 'send'), 'send')]"
                )
        except Exception:
            pass

        for s in candidates:
            txt = (s.text or "").strip().lower()
            cls = (s.get_attribute("class") or "").lower()
            if visible(s) and ("save" in txt or "send" in txt or "send" in cls or "save" in cls):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", s)
                    time.sleep(0.3)
                except Exception:
                    pass
                try:
                    ActionChains(driver).move_to_element(s).click().perform()
                    save_clicked = True
                    break
                except Exception:
                    pass
                try:
                    driver.execute_script("""
                        arguments[0].classList.remove('disabled');
                        arguments[0].removeAttribute('disabled');
                        arguments[0].click();
                    """, s)
                    save_clicked = True
                    break
                except Exception:
                    pass

        if not save_clicked:
            save_btns = drawer.find_elements(By.CSS_SELECTOR, ".sendMsg, .send, [id^='sendMsg__']")
            for s in save_btns:
                if visible(s):
                    driver.execute_script("arguments[0].classList.remove('disabled'); arguments[0].removeAttribute('disabled'); arguments[0].click();", s)
                    save_clicked = True
                    break



        time.sleep(2)
        return "acted"
    except Exception as e:
        log.debug(f"Transient DOM update during chat step: {e}")
        time.sleep(1.5)
        return "acted"


# --------------------------------------------------------------------------- applying one job
def verify_on_job_page(driver, url: str) -> bool:
    if url and "job-listings" in url:
        driver.get(url)
    for _ in range(5):
        time.sleep(2)
        if is_applied(driver):
            return True
    return False


def complete_application(driver, job: dict):
    time.sleep(4)
    dismiss_popups(driver)
    host = urlparse(driver.current_url).netloc.lower()
    if host and "naukri.com" not in host:
        return "failed", f"redirected to external site ({host})"
    if not on_job_page(driver):
        return "failed", "card click did not open a job page"
    if is_applied(driver):
        return "already_applied", "job page already shows Applied"
    if not click_apply_button(driver):
        return "failed", "no Quick apply button on the job page"

    seen, quiet = {}, 0
    for _ in range(60):
        time.sleep(2)
        host = urlparse(driver.current_url).netloc.lower()
        if host and "naukri.com" not in host:
            return "failed", f"redirected to external site ({host})"
        if "login" in driver.current_url.lower():
            return "failed", "bounced to login page"

        # 1. Check if questionnaire drawer is open
        drawer = find_chat_drawer(driver)
        if drawer and drawer.is_displayed():
            quiet = 0
            step = chat_step(driver, drawer, seen)
            if step.startswith("stuck:"):
                return "failed", step[6:]
            if step == "completed":
                for _ in range(5):
                    time.sleep(2)
                    if is_applied(driver):
                        return "applied", _shot_note(driver, job)
                    if not (drawer and drawer.is_displayed()):
                        break
                    for x in drawer.find_elements(By.CSS_SELECTOR, ".crossIcon, .chatBot-ic-cross, .cross, .close, [class*='close'], [class*='cross']"):
                        try:
                            if x.is_displayed():
                                x.click()
                                break
                        except Exception:
                            pass
            continue

        # 2. Check if already successfully applied (no active questions, green confirmation)
        if is_applied(driver):
            return "applied", _shot_note(driver, job)

        quiet += 1
        if quiet >= 6:
            break

    if is_applied(driver):
        return "applied", _shot_note(driver, job)
    if verify_on_job_page(driver, job.get("url", "")):
        return "applied", _shot_note(driver, job)
    return "failed", "no 'Applied' confirmation seen"



def _shot_note(driver, job):
    time.sleep(1)
    path = snap_applied(driver, job)
    return f"confirmed; screenshot: {path}" if path else "confirmed"


def apply_to(driver, job: dict):
    main = driver.current_window_handle
    before = set(driver.window_handles)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", job["button"])
    time.sleep(1)
    try:
        ActionChains(driver).move_to_element(job["button"]).click().perform()
    except Exception:
        driver.execute_script("arguments[0].click();", job["button"])
    time.sleep(3)
    new = set(driver.window_handles) - before
    if new:
        driver.switch_to.window(next(iter(new)))

    card_id = job.get("id")
    # Update job ID and URL from opened tab
    real_url = driver.current_url
    real_id = job_id_from_url(real_url)
    if real_id:
        job["id"] = real_id
        job["card_id"] = card_id
        job["url"] = real_url

    try:
        status, note = complete_application(driver, job)
        if status == "failed":
            snap(driver, f"failed_{job['id']}")
        return status, note
    finally:
        for h in list(driver.window_handles):
            if h != main and h not in before:
                try:
                    driver.switch_to.window(h)
                    driver.close()
                except Exception:
                    pass
        try:
            driver.switch_to.window(main)
        except Exception:
            pass


# --------------------------------------------------------------------------- main loop
class RunTracker:
    def __init__(self, target: int):
        self.target = target
        self.applied_this_run = 0


def run(driver, state, tracker: RunTracker) -> int:
    target_str = "unlimited" if UNLIMITED else str(tracker.target)
    log.info(f"Goal for this run: {target_str} fresh jobs (already applied today: {applied_today(state)}).")
    if MAX_RUN_MINUTES > 0:
        log.info(f"Time cap enabled: run will gracefully finish after max {MAX_RUN_MINUTES} minutes.")

    attempted, attempts = set(), 0
    run_start_time = time.time()
    for location, age in search_plan():
        if MAX_RUN_MINUTES > 0 and (time.time() - run_start_time) >= (MAX_RUN_MINUTES * 60):
            log.info(f"Reached MAX_RUN_MINUTES limit ({MAX_RUN_MINUTES} mins). Saving progress and stopping run cleanly.")
            return tracker.applied_this_run
        for query in QUERIES:
            if MAX_RUN_MINUTES > 0 and (time.time() - run_start_time) >= (MAX_RUN_MINUTES * 60):
                log.info(f"Reached MAX_RUN_MINUTES limit ({MAX_RUN_MINUTES} mins). Saving progress and stopping run cleanly.")
                return tracker.applied_this_run
            for page in range(1, MAX_PAGES + 1):
                if MAX_RUN_MINUTES > 0 and (time.time() - run_start_time) >= (MAX_RUN_MINUTES * 60):
                    log.info(f"Reached MAX_RUN_MINUTES limit ({MAX_RUN_MINUTES} mins). Saving progress and stopping run cleanly.")
                    return tracker.applied_this_run
                url = build_url(query, page, age, location)
                log.info(f"[{query!r} | {location or 'anywhere in India'} | last {age}d | page {page}]")
                cards = []
                while (UNLIMITED or tracker.applied_this_run < tracker.target) and attempts < MAX_ATTEMPTS:
                    if MAX_RUN_MINUTES > 0 and (time.time() - run_start_time) >= (MAX_RUN_MINUTES * 60):
                        log.info(f"Reached MAX_RUN_MINUTES limit ({MAX_RUN_MINUTES} mins). Saving progress and stopping run cleanly.")
                        del cards
                        gc.collect()
                        return tracker.applied_this_run
                    cards = load_cards(driver, url)
                    if not cards:
                        break
                    fresh = []
                    applied_pairs = {
                        (j.get("title", "").strip().lower(), j.get("company", "").strip().lower())
                        for j in state["jobs"].values()
                        if j.get("status") in ("applied", "already_applied")
                    }
                    for c in cards:
                        if c["id"] in state["jobs"] or c["id"] in attempted:
                            continue
                        pair = (c["title"].strip().lower(), c["company"].strip().lower())
                        if pair[0] and pair[1] and pair in applied_pairs:
                            continue
                        if c["age"] is not None and c["age"] > age:
                            continue
                        fresh.append(c)
                    if not fresh:
                        break
                    job = fresh[0]
                    attempted.add(job["id"])
                    attempts += 1
                    log.info(f"  -> {job['title']!r} @ {job['company']!r} (id {job['id']}, age {job['age']}d)")
                    try:
                        status, note = apply_to(driver, job)
                    except Exception as e:
                        if any(term in str(e).lower() for term in ("invalid session", "disconnected", "no such window", "crashed", "timed out", "timeout")):
                            raise
                        status, note = "failed", f"error: {e}"
                    record(state, job, status, note)
                    if status == "applied":
                        tracker.applied_this_run += 1
                        log.info(f"  OK  applied {tracker.applied_this_run}/{target_str} this run (total today: {applied_today(state)})  [{note}]")
                        print(f"\n" + "=" * 55)
                        print(f">>> [SUCCESS] Applied to job #{tracker.applied_this_run} of {target_str} this run")
                        print(f">>> Title  : {job['title']}")
                        print(f">>> Company: {job['company']}")
                        print(f">>> Progress: {tracker.applied_this_run} / {target_str} applied (Total today: {applied_today(state)})")
                        print("=" * 55 + "\n")
                    elif status == "already_applied":
                        log.info("  SKIP already applied (ignored)")
                    else:
                        log.warning(f"  SKIP not counted: {note}")
                if (not UNLIMITED and tracker.applied_this_run >= tracker.target) or attempts >= MAX_ATTEMPTS:
                    del cards
                    gc.collect()
                    return tracker.applied_this_run
                if not cards:
                    break
            del cards
            gc.collect()
    return tracker.applied_this_run


def prompt_user_inputs():
    """Interactively prompts user for job target and location preference only if --interactive is passed."""
    global JOBS_PER_RUN, LOCATION, UNLIMITED, MAX_ATTEMPTS
    if not any(a in sys.argv for a in ("--interactive", "--prompt")):
        return

    has_cli_target = len(sys.argv) > 1 and sys.argv[1].isdigit()
    has_cli_loc = any(a in sys.argv for a in ("--no-location", "--location")) or any(a.startswith("--location=") for a in sys.argv)

    if not (has_cli_target and has_cli_loc) and sys.stdin.isatty():
        print("\n" + "=" * 60)
        print("          NAUKRI JOB APPLY BOT CONFIGURATION")
        print("=" * 60)

        # 1. Ask how many jobs
        if not has_cli_target:
            try:
                user_val = input(f"\nHow many jobs do you want to apply to? [Default: {JOBS_PER_RUN}]: ").strip()
                if user_val.isdigit() and int(user_val) > 0:
                    JOBS_PER_RUN = int(user_val)
            except (EOFError, KeyboardInterrupt):
                pass

        # 2. Ask location preference
        if not has_cli_loc:
            print("\nChoose Location Mode:")
            print("  [1] Without Location (Apply to all of India / Remote / Everywhere)")
            print("  [2] With Location - Bangalore (Default)")
            print("  [3] With Location - Custom city")
            try:
                choice = input("Enter option [1, 2, or 3] (Default: 1): ").strip()
                if choice == "2":
                    LOCATION = "Bangalore"
                elif choice == "3":
                    city = input("Enter city name (e.g. Hyderabad, Pune, Mumbai): ").strip()
                    LOCATION = city or "Bangalore"
                else:
                    LOCATION = ""
            except (EOFError, KeyboardInterrupt):
                LOCATION = ""

        print("\n" + "-" * 60)
        print(f" Target Jobs : {JOBS_PER_RUN}")
        print(f" Location    : {LOCATION or 'Anywhere in India (No location filter)'}")
        print("-" * 60 + "\n")

        UNLIMITED = JOBS_PER_RUN <= 0
        MAX_ATTEMPTS = 1000 if UNLIMITED else max(500, JOBS_PER_RUN * 4)


def main():
    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        if not (COOKIES_FILE.exists() or NAUKRI_COOKIES):
            log.error("Missing NAUKRI_EMAIL / NAUKRI_PASSWORD and cookies in .env")
            sys.exit(2)
    prompt_user_inputs()
    clean_screenshots()
    state = load_state()
    tracker = RunTracker(JOBS_PER_RUN)
    target_str = "unlimited" if UNLIMITED else str(tracker.target)

    max_restarts = 5
    restart_count = 0
    while (UNLIMITED or tracker.applied_this_run < tracker.target) and restart_count < max_restarts:
        driver = None
        try:
            driver = get_driver()
            if not ensure_login(driver):
                sys.exit(3)
            run(driver, state, tracker)
            break
        except Exception as e:
            restart_count += 1
            log.warning(f"Browser encountered an issue ({e}). Auto-recovering (attempt {restart_count}/{max_restarts})...")
            time.sleep(3)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                try:
                    if hasattr(driver, "service") and driver.service and driver.service.process:
                        driver.service.process.kill()
                except Exception:
                    pass
                del driver
            gc.collect()

    # Final post-run cleanup (cleans accumulated cache, session temp dirs, and runs GC)
    try:
        clean_artifacts()
    except Exception:
        pass
    gc.collect()

    print("\n" + "=" * 60)
    print("                RUN COMPLETION SUMMARY")
    print("=" * 60)
    print(f"  Jobs applied this run : {tracker.applied_this_run} / {target_str}")
    print(f"  Total applied today   : {applied_today(state)}")
    print(f"  Screenshots folder    : {APPLIED_SHOTS_DIR}")
    print("=" * 60 + "\n")
    log.info(f"Applied in this run: {tracker.applied_this_run}/{target_str} (Total today: {applied_today(state)})   (screenshots in {APPLIED_SHOTS_DIR})")
    if not UNLIMITED and tracker.applied_this_run < tracker.target:
        log.warning("Run target NOT met - ran out of fresh Quick-apply jobs or hit questions it will not guess. "
                    "Check applied_jobs.json ('failed' entries) and screenshots/failed_*.png for the reason.")


if __name__ == "__main__":
    main()
