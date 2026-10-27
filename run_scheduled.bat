@echo off
rem ==============================================================================
rem Automated Twice-Daily Scheduled Runner for Naukri Job Apply Bot
rem Completely non-interactive: no user prompts, no Read-Host, no pause.
rem Includes automatic memory, process, and log rotation cleanup.
rem ==============================================================================
cd /d "%~dp0"

rem Ensure logs directory exists
if not exist "logs" mkdir "logs"

rem Rotate scheduled_task.log if larger than 5MB (5242880 bytes)
if exist "logs\scheduled_task.log" (
    for %%F in ("logs\scheduled_task.log") do (
        if %%~zF GTR 5242880 (
            move /Y "logs\scheduled_task.log" "logs\scheduled_task.log.old" >nul 2>&1
        )
    )
)

rem Pre-run process cleanup: terminate any orphaned WebDriver daemons
taskkill /F /IM msedgedriver.exe >nul 2>&1
taskkill /F /IM chromedriver.exe >nul 2>&1

echo [%DATE% %TIME%] Starting scheduled Naukri Job Apply Bot run... >> "logs\scheduled_task.log" 2>&1

rem Detect Python executable
set "PYTHON_EXE=python"
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    if exist "C:\Users\malla\AppData\Local\Programs\Python\Python312\python.exe" (
        set "PYTHON_EXE=C:\Users\malla\AppData\Local\Programs\Python\Python312\python.exe"
    )
)

rem Execute the bot
"%PYTHON_EXE%" daily_apply.py >> "logs\scheduled_task.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%

rem Post-run cleanup: ensure no orphaned driver processes remain in RAM
taskkill /F /IM msedgedriver.exe >nul 2>&1
taskkill /F /IM chromedriver.exe >nul 2>&1

echo [%DATE% %TIME%] Scheduled run finished with exit code %EXIT_CODE%. >> "logs\scheduled_task.log" 2>&1
exit /b %EXIT_CODE%
