@echo off
title Naukri Job Apply Bot - Manual Run
cd /d "%~dp0"
echo ========================================================
echo               Naukri Job Apply Bot - Run Now
echo ========================================================
python daily_apply.py
echo.
echo Finished. Press any key to exit.
pause >nul
