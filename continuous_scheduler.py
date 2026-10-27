"""Continuous Background Scheduler for Naukri Job Apply Bot.

Runs automatically twice every day (09:30 AM and 05:30 PM IST)
without any manual prompts or interaction.
"""
import gc
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "logs" / "continuous_scheduler.log"

BASE_DIR.joinpath("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("Scheduler")

# Scheduled times (24-hour format HH:MM)
SCHEDULED_TIMES = ["09:30", "17:30"]


def run_apply_job():
    log.info("=" * 60)
    log.info("Triggering scheduled Naukri Job Apply run (non-interactive)...")
    log.info("=" * 60)
    try:
        # Pre-cleanup
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "msedgedriver.exe"], capture_output=True)
            subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"], capture_output=True)

        cmd = [sys.executable, str(BASE_DIR / "daily_apply.py")]
        result = subprocess.run(cmd, cwd=str(BASE_DIR))
        log.info(f"Scheduled run completed with exit code: {result.returncode}")

        # Post-cleanup: terminate dangling webdriver and run garbage collector
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "msedgedriver.exe"], capture_output=True)
            subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"], capture_output=True)
        gc.collect()
    except Exception as e:
        log.error(f"Error executing scheduled apply job: {e}")


def main():
    log.info("=" * 60)
    log.info("Naukri Twice-Daily Background Scheduler Started")
    log.info(f"Scheduled times: {', '.join(SCHEDULED_TIMES)} daily")
    log.info("No manual interaction required.")
    log.info("=" * 60)

    last_run_time_slot = ""

    while True:
        now_str = datetime.now().strftime("%H:%M")
        today_date = datetime.now().strftime("%Y-%m-%d")

        if now_str in SCHEDULED_TIMES:
            current_slot = f"{today_date}_{now_str}"
            if last_run_time_slot != current_slot:
                last_run_time_slot = current_slot
                run_apply_job()

        time.sleep(30)


if __name__ == "__main__":
    main()
