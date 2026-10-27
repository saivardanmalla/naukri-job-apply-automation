param(
    [int]$Target = 0,
    [string]$Location = "",
    [switch]$Interactive
)

Set-Location -Path $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "        NAUKRI JOB APPLY AUTOMATION ASSISTANT             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

if ($Interactive) {
    # 1. Ask how many jobs to apply
    $defaultJobs = 50
    $jobsInput = Read-Host "How many jobs do you want to apply to? [Default: $defaultJobs]"
    if ([string]::IsNullOrWhiteSpace($jobsInput) -or -not ($jobsInput -as [int])) {
        $targetJobs = $defaultJobs
    } else {
        $targetJobs = [int]$jobsInput
    }

    # 2. Ask with location or without location
    Write-Host "`nChoose Location Mode:" -ForegroundColor Yellow
    Write-Host "  [1] Without Location (Apply to all of India / Remote / Everywhere)" -ForegroundColor White
    Write-Host "  [2] With Location - Bangalore (Default)" -ForegroundColor White
    Write-Host "  [3] With Location - Custom city name" -ForegroundColor White
    $locChoice = Read-Host "Select option [1, 2, or 3] (Default: 1)"

    if ($locChoice -eq "2") {
        $locArgs = @("--location", "Bangalore")
    } elseif ($locChoice -eq "3") {
        $customCity = Read-Host "Enter City / Location name (e.g. Hyderabad, Pune, Mumbai)"
        if ([string]::IsNullOrWhiteSpace($customCity)) {
            $customCity = "Bangalore"
        }
        $locArgs = @("--location", "$customCity")
    } else {
        $locArgs = @("--no-location")
    }

    python daily_apply.py $targetJobs @locArgs
} else {
    $cliArgs = @()
    if ($Target -gt 0) {
        $cliArgs += "$Target"
    }
    if ($Location -eq "none" -or $Location -eq "all") {
        $cliArgs += "--no-location"
    } elseif (![string]::IsNullOrWhiteSpace($Location) -and $Location -ne "PROMPT") {
        $cliArgs += @("--location", "$Location")
    }

    Write-Host "Starting automation directly using configuration in .env..." -ForegroundColor Green
    python daily_apply.py @cliArgs
}

Write-Host ""
Read-Host "Execution finished. Press Enter to exit..."
