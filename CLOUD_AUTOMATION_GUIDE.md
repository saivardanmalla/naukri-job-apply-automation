# 🚀 Naukri Job Apply Bot — Twice-Daily Cron Automation Guide

This guide details the complete 24/7 automation setup for **Naukri Job Apply Automation**, configured to mirror the cloud architecture of `naukri-daily-updater`.

---

## ⏰ Cron Schedule: Twice Daily (9:30 AM & 5:30 PM IST)

| Run Slot | Time (IST) | Time (UTC) | GitHub Actions Cron Expression |
| :--- | :--- | :--- | :--- |
| **Morning Run** | **09:30 AM IST** | `04:00 UTC` | `0 4 * * *` |
| **Evening Run** | **05:30 PM IST** | `12:00 UTC` | `0 12 * * *` |
| **Combined** | **9:30 AM & 5:30 PM** | `04:00 & 12:00 UTC` | `0 4,12 * * *` |

> [!NOTE]
> Indian Standard Time (IST) is **UTC + 5:30**. 
> - 09:30 AM IST − 5:30 = **04:00 UTC**
> - 05:30 PM IST (17:30) − 5:30 = **12:00 UTC**

---

## 🛠️ What Was Configured (Matching `naukri-daily-updater`)

1. **GitHub Actions Cloud Workflows (`.github/workflows/`)**:
   - [naukri_apply.yml](file:///c:/Users/malla/Downloads/naukri_job_apply_automation/.github/workflows/naukri_apply.yml): Executes twice daily on cron (`0 4,12 * * *`), with `workflow_dispatch` for manual on-demand triggers.
   - [cleanup_runs.yml](file:///c:/Users/malla/Downloads/naukri_job_apply_automation/.github/workflows/cleanup_runs.yml): Purges old workflow runs daily so your repository storage stays free.
2. **Multi-Browser & Cross-Platform Support**:
   - [daily_apply.py](file:///c:/Users/malla/Downloads/naukri_job_apply_automation/daily_apply.py) now supports both **Google Chrome** (default on Linux / GitHub Actions) and **Microsoft Edge** (Windows).
   - Pre-configured with `--no-sandbox`, `--disable-dev-shm-usage`, and `--headless=new` for headless cloud execution.
3. **Session Cookie Injection & Zero-Intervention Auth**:
   - Bypasses OTP / CAPTCHA completely by injecting saved cookies (`cookies.json` or `NAUKRI_COOKIES` secret).
4. **Quick Helpers**:
   - [copy_cookies_to_clipboard.bat](file:///c:/Users/malla/Downloads/naukri_job_apply_automation/copy_cookies_to_clipboard.bat): Double-click to instantly copy your session cookies to your Windows clipboard.
   - [run_now.bat](file:///c:/Users/malla/Downloads/naukri_job_apply_automation/run_now.bat): One-click manual test run.
5. **Local Backup**:
   - Windows Task Scheduler task `NaukriTwiceDailyApplyBot` is already armed locally for 9:30 AM and 5:30 PM IST.

---

## 📋 3-Step Setup for GitHub Cloud Execution

### Step 1: Copy Your Session Cookies
Double-click [copy_cookies_to_clipboard.bat](file:///c:/Users/malla/Downloads/naukri_job_apply_automation/copy_cookies_to_clipboard.bat).
This copies the contents of your `cookies.json` directly to your clipboard.

### Step 2: Add Secrets to Your GitHub Repository
1. Open your repository on GitHub: `https://github.com/saivardanmalla/AI-Coding-Agent` (or your dedicated bot repo).
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Add the following **Repository Secrets**:
   * `NAUKRI_EMAIL`: Your Naukri account email.
   * `NAUKRI_PASSWORD`: Your Naukri account password.
   * `NAUKRI_COOKIES`: Paste the copied cookies from Step 1.
   * *(Optional)* `RESUME_BASE64`: If you want to supply an encrypted resume instead of using the repository's `resume.pdf`.

### Step 3: Push Changes to GitHub
Push this directory to your GitHub repository:
```bash
git add .
git commit -m "Configure 9:30 AM and 5:30 PM cron automation like naukri-daily-updater"
git push origin main
```

---

## 🌐 (Optional) Connect cron-job.org for Exact-Second Cloud Triggering

Just like in `naukri-daily-updater`:
* GitHub's free-tier scheduled cron runs can occasionally experience slight queuing delays during peak hours.
* If you want execution down to the exact second (even when your laptop is turned off):
  1. Open [console.cron-job.org](https://console.cron-job.org).
  2. Create a new job:
     * **URL:** `https://api.github.com/repos/<USERNAME>/<REPO>/actions/workflows/naukri_apply.yml/dispatches`
     * **Method:** `POST`
     * **Headers:**
       * `Authorization`: `Bearer <YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>`
       * `Accept`: `application/vnd.github.v3+json`
     * **Body:** `{"ref": "main"}`
     * **Schedule:** Daily at `09:30` and `17:30` (Timezone: `Asia/Kolkata`).

---

## 📱 How to Monitor Runs
* **On GitHub Actions:** Open the **Actions** tab in your repository to watch live logs and download zip artifacts containing all screenshots (`Applied ✓`) and execution logs.
* **Locally:** Logs are stored in `logs/scheduled_task.log` and `logs/daily_apply.log`.

---

## ⚡ GitHub Actions Minutes & Quota Protection

GitHub provides **2,000 free runner minutes per month** for private repositories (usage resets on the 1st of every month).

To ensure you **never run out of minutes** or get charged:
1. **Quota-Optimized Execution**:
   - Each cloud run is capped at **10 fresh jobs** and **10 minutes max runtime** (`timeout-minutes: 15`).
   - 2 runs/day = ~15–20 minutes/day = ~450–600 minutes/month total (leaving plenty of buffer from your 2,000 limit).
2. **Prevent Accidental Charges ($0 Spending Limit)**:
   - Go to your GitHub account: **Settings** > **Billing and plans** > **Cost Management / Spending limits**.
   - Make sure **Actions** spending limit is set to **$0** (default). GitHub will NEVER charge your card.
3. **Want Unlimited Free Minutes Forever?**
   - GitHub gives **100% UNLIMITED FREE Actions minutes** to **Public repositories**.
   - If you want to switch your repository to Public, remove `cookies.json` from git and keep secrets strictly in GitHub Repository Secrets.
