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
Write-Host "Schedule    : Twice Daily (09:30 AM & 05:30 PM IST)" -ForegroundColor White
Write-Host "Mode        : Fully Automated (Zero Manual Interaction)" -ForegroundColor White
Write-Host ""

# Action: Use silent VBS wrapper if present, otherwise direct bat
if (Test-Path $vbsPath) {
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbsPath`"" -WorkingDirectory $scriptDir
} else {
    $action = New-ScheduledTaskAction -Execute $actionPath -WorkingDirectory $scriptDir
}

# Triggers:
# 1. Morning Run at 09:30 AM
$triggerMorning = New-ScheduledTaskTrigger -Daily -At "09:30"

# 2. Evening Run at 05:30 PM (17:30)
$triggerEvening = New-ScheduledTaskTrigger -Daily -At "17:30"

# Settings:
# - Run on battery or AC power
# - Catch up if run was missed while laptop was powered off / asleep
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
    -Description "Automated Naukri Job Apply Bot - runs twice daily without manual interaction" `
    -Force | Out-Null

Write-Host "SUCCESS: Task '$taskName' successfully registered!" -ForegroundColor Green
Write-Host ""
Write-Host "Scheduled Times:" -ForegroundColor Yellow
Write-Host "  [1] Morning Run : 09:30 AM every day" -ForegroundColor White
Write-Host "  [2] Evening Run : 05:30 PM every day" -ForegroundColor White
Write-Host ""
Write-Host "Fail-Safe Features Enabled:" -ForegroundColor Cyan
Write-Host "  [OK] Battery support (runs even if laptop is on battery)" -ForegroundColor Gray
Write-Host "  [OK] Missed run catch-up (runs upon boot/wake if time was missed)" -ForegroundColor Gray
Write-Host "  [OK] Silent execution (no flashing console or popup windows)" -ForegroundColor Gray
Write-Host "  [OK] Zero manual intervention (all inputs read from .env)" -ForegroundColor Gray
Write-Host "  [OK] Output logged to logs\daily_apply.log & logs\scheduled_task.log" -ForegroundColor Gray
