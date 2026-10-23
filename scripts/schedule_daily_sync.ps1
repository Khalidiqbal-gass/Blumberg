# Automated 4:30 PM IST End-of-Day (EOD) Market Sync Task for Windows
# Registers a Windows Scheduled Task or executes manual EOD batch sync immediately

param (
    [switch]$InstallTask,
    [switch]$RunNow
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SyncScript = Join-Path $ProjectRoot "scripts\run_daily_eod_automation.py"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Blumberg Market Radar - 4:30 PM EOD Automation Manager" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

if ($InstallTask) {
    Write-Host "`nRegistering Windows Scheduled Task for 4:30 PM IST (Mon-Fri)..." -ForegroundColor Yellow
    $TaskName = "Blumberg_Market_Radar_EOD_Sync"
    $Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$SyncScript`"" -WorkingDirectory $ProjectRoot
    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 16:30
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily 4:30 PM EOD Market Data Sync and Alert Dispatcher" -Force
        Write-Host "Scheduled Task '$TaskName' registered successfully for 4:30 PM IST on trading days!" -ForegroundColor Green
    } catch {
        Write-Host "Could not register task via standard user: $_" -ForegroundColor Yellow
        Write-Host "Tip: Run PowerShell as Administrator to install the Windows background service." -ForegroundColor Yellow
    }
}

if ($RunNow -or (-not $InstallTask)) {
    Write-Host "`nLaunching EOD Automation now..." -ForegroundColor Yellow
    Set-Location $ProjectRoot
    & $PythonExe $SyncScript
}
