# Automated 4:00 PM IST End-of-Day (EOD) Market Sync Task for Windows
# Registers a Windows Scheduled Task or executes manual EOD batch sync immediately

param (
    [switch]$InstallTask,
    [switch]$RunNow,
    [int]$MaxStocks = 0
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SyncScript = Join-Path $ProjectRoot "scripts\sync_eod_market.py"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "⚡ Blumberg Market Radar — 4:00 PM EOD Batch Sync Manager" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

if ($InstallTask) {
    Write-Host "`nRegistering Windows Scheduled Task for 4:00 PM IST (Mon-Fri)..." -ForegroundColor Yellow
    $TaskName = "Blumberg_Market_Radar_EOD_Sync"
    $Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$SyncScript`" --all" -WorkingDirectory $ProjectRoot
    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 16:00
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily 4:00 PM EOD Market Data Sync & Intelligence Digest" -Force
        Write-Host "✅ Scheduled Task '$TaskName' registered successfully for 4:00 PM IST on trading days!" -ForegroundColor Green
    } catch {
        Write-Host "❌ Failed to register task: $_" -ForegroundColor Red
        Write-Host "Note: You can run PowerShell as Administrator to register Windows Scheduled Tasks, or use -RunNow for manual runs." -ForegroundColor Yellow
    }
}

if ($RunNow -or (-not $InstallTask)) {
    Write-Host "`nLaunching EOD Batch Sync now..." -ForegroundColor Yellow
    $ExecArgs = @()
    if ($MaxStocks -gt 0) {
        $ExecArgs += "--max"
        $ExecArgs += "$MaxStocks"
    } else {
        $ExecArgs += "--all"
    }

    Write-Host "Command: & `"$PythonExe`" `"$SyncScript`" $ExecArgs" -ForegroundColor DarkGray
    Set-Location $ProjectRoot
    & $PythonExe $SyncScript @ExecArgs
}
