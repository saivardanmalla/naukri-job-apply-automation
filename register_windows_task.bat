@echo off
title Register Naukri Twice-Daily Apply Bot (9 AM & 4 PM)
cd /d "%~dp0"

echo ======================================================================
echo    Scheduling Naukri Job Apply Bot (9:00 AM & 4:00 PM, 100 Jobs)
echo ======================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_robust_task.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo PowerShell configuration encountered an error. Falling back to basic schtasks...
    schtasks /create /tn "NaukriTwiceDailyApplyBot_Morning" /tr "\"%~dp0run_scheduled.bat\"" /sc daily /st 09:00 /f
    schtasks /create /tn "NaukriTwiceDailyApplyBot_Evening" /tr "\"%~dp0run_scheduled.bat\"" /sc daily /st 16:00 /f
)

echo.
pause
