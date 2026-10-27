@echo off
title Disable Naukri Twice-Daily Apply Bot
cd /d "%~dp0"

echo Disabling and removing scheduled tasks...
schtasks /delete /tn "NaukriTwiceDailyApplyBot" /f >nul 2>&1
schtasks /delete /tn "NaukriTwiceDailyApplyBot_Morning" /f >nul 2>&1
schtasks /delete /tn "NaukriTwiceDailyApplyBot_Evening" /f >nul 2>&1

echo.
echo Scheduled tasks successfully removed!
echo.
pause
