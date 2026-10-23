# ==============================================================================
# Blumberg Market Radar — Nightly EOD Automation One-Click Runner
# ==============================================================================
# Usage:
#   .\scripts\run_nightly_pipeline.ps1
#   .\scripts\run_nightly_pipeline.ps1 -Mode live
#
# Suitable for Windows Task Scheduler:
#   Program: powershell.exe
#   Arguments: -ExecutionPolicy Bypass -File "scripts\run_nightly_pipeline.ps1" -Mode offline
# ==============================================================================

[CmdletBinding()]
param(
    [ValidateSet("offline", "live")]
    [string]$Mode = "offline",

    [string]$OutputDir = "reports/daily_digests",

    [string]$LedgerPath = "data/signal_ledger.jsonl",

    [double]$MinScore = 50.0,

    [double]$MinTurnover = 1.0,

    [string]$Date = ""
)

$ErrorActionPreference = "Stop"

# Set Project Root
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "📡 Blumberg Market Radar — Automated Nightly EOD Pipeline Runner" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"
Write-Host "Mode:         $Mode"
Write-Host "Timestamp:    $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# Locate Python Executable in virtual environment
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
    Write-Warning "Virtual environment python not found at .venv\Scripts\python.exe. Falling back to system python: $PythonExe"
}

# Build arguments array
$ScriptPath = Join-Path $ProjectRoot "scripts\nightly_eod_pipeline.py"
$ArgList = @(
    $ScriptPath,
    "--mode", $Mode,
    "--output", $OutputDir,
    "--ledger", $LedgerPath,
    "--min-score", $MinScore.ToString(),
    "--min-turnover", $MinTurnover.ToString()
)

if ($Date -ne "") {
    $ArgList += @("--date", $Date)
}

Write-Host "`nExecuting: $PythonExe $($ArgList -join ' ')" -ForegroundColor Yellow

# Execute python pipeline
& $PythonExe $ArgList
$ExitCode = $LASTEXITCODE

if ($ExitCode -eq 0) {
    Write-Host "`n[SUCCESS] Nightly EOD pipeline finished with exit code 0." -ForegroundColor Green
} else {
    Write-Host "`n[FAILURE] Nightly EOD pipeline terminated with error code $ExitCode." -ForegroundColor Red
}

exit $ExitCode
