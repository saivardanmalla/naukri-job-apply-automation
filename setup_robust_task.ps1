# ==============================================================================
# Robust Windows Task Scheduler Setup for Naukri Twice-Daily Apply Bot
# ==============================================================================
$ErrorActionPreference = "Stop"

$taskName = "NaukriTwiceDailyApplyBot"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$actionPath = Join-Path $scriptDir "run_scheduled.bat"
$vbsPath = Join-Path $scriptDir "run_silent.vbs"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Setting up Twice-Daily Scheduled Task for Naukri Apply " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Task Name   : $taskName" -ForegroundColor White
Write-Host "Directory   : $scriptDir" -ForegroundColor White
Write-Host "Schedule    : Twice Daily (09:00 AM & 04:00 PM IST)" -ForegroundColor White
Write-Host "Target      : 100 Jobs / run (Headless Mode)" -ForegroundColor White
Write-Host "Mode        : Fully Automated (Zero Manual Interaction)" -ForegroundColor White
Write-Host ""

# Action: Use silent VBS wrapper so no console pops up
if (Test-Path $vbsPath) {
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbsPath`"" -WorkingDirectory $scriptDir
} else {
    $action = New-ScheduledTaskAction -Execute $actionPath -WorkingDirectory $scriptDir
}

# Triggers:
# 1. Morning Run at 09:00 AM
$triggerMorning = New-ScheduledTaskTrigger -Daily -At "09:00"

# 2. Evening Run at 04:00 PM (16:00)
$triggerEvening = New-ScheduledTaskTrigger -Daily -At "16:00"

# Settings:
# - Run on battery or AC power
# - Catch up if run was missed while laptop was off/asleep
# - Single instance execution
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Register or replace the task
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($triggerMorning, $triggerEvening) `
    -Settings $settings `
    -Description "Automated Naukri Job Apply Bot - runs twice daily (9 AM & 4 PM) applying 100 jobs in headless mode" `
    -Force | Out-Null

Write-Host "SUCCESS: Task '$taskName' successfully registered!" -ForegroundColor Green
Write-Host ""
Write-Host "Scheduled Times:" -ForegroundColor Yellow
Write-Host "  [1] Morning Run : 09:00 AM every day" -ForegroundColor White
Write-Host "  [2] Evening Run : 04:00 PM every day" -ForegroundColor White
Write-Host ""
Write-Host "Features Active:" -ForegroundColor Cyan
Write-Host "  [OK] Headless Execution (runs quietly in background)" -ForegroundColor Gray
Write-Host "  [OK] 100 Jobs target per run" -ForegroundColor Gray
Write-Host "  [OK] Battery support (runs even if laptop is on battery)" -ForegroundColor Gray
Write-Host "  [OK] Missed run catch-up (runs upon boot/wake if time was missed)" -ForegroundColor Gray
Write-Host "  [OK] Logs stored in logs\scheduled_task.log and logs\daily_apply.log" -ForegroundColor Gray
