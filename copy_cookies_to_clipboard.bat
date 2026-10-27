@echo off
title Copy Naukri Cookies to Clipboard
cd /d "%~dp0"

powershell -NoProfile -Command "$f = if (Test-Path 'cookies.json') { 'cookies.json' } else { $null }; if ($f) { Get-Content $f -Raw | Set-Clipboard; Write-Host 'Success: Session cookies copied to clipboard!' -ForegroundColor Green; Write-Host 'Paste directly into GitHub Secret: NAUKRI_COOKIES' -ForegroundColor Yellow } else { Write-Host 'cookies.json not found! Run the bot once to generate cookies.' -ForegroundColor Red }"
echo.
pause
