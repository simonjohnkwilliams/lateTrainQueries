<#
.SYNOPSIS
  Register Friday + daily catch-up Task Scheduler jobs for weekly Delay Repay ops (FR32).

.DESCRIPTION
  Creates two tasks under the current user (no cloud scheduler — NFR12):

    LateTrainQueries-WeeklyOps-Friday   — weekly on Friday at -At time
    LateTrainQueries-WeeklyOps-CatchUp  — daily at -CatchUpAt (missed-Friday catch-up)

  Both invoke scripts\weekly_ops.ps1. The Python completion marker (FR39) makes
  catch-up a no-op when the anchor Friday already completed.

  Note: true "At log on" tasks usually need an elevated PowerShell. Daily catch-up
  covers the same FR32 intent without admin. Optional -PreferLogon tries ONLOGON.

.PARAMETER At
  Local time for the Friday trigger (default 18:00).

.PARAMETER CatchUpAt
  Local time for the daily catch-up trigger (default 09:30).

.PARAMETER ProjectRoot
  Repo root (default: parent of scripts/).

.PARAMETER PreferLogon
  Try ONLOGON instead of daily catch-up (often requires Admin).

.PARAMETER Unregister
  Remove the scheduled tasks instead of creating them.
#>
[CmdletBinding()]
param(
    [string] $At = "18:00",
    [string] $CatchUpAt = "09:30",
    [string] $ProjectRoot = "",
    [switch] $PreferLogon,
    [switch] $Unregister
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$runner = Join-Path $ProjectRoot "scripts\weekly_ops.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    Write-Error "Missing runner: $runner"
    exit 2
}

$taskFriday = "LateTrainQueries-WeeklyOps-Friday"
$taskCatchUp = "LateTrainQueries-WeeklyOps-CatchUp"
$taskLogon = "LateTrainQueries-WeeklyOps-Logon"
$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runner`""

function Remove-WeeklyTask([string] $Name) {
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "Removed task: $Name"
    }
    else {
        # Also try schtasks in case CIM name differs
        schtasks.exe /Delete /F /TN $Name 2>$null | Out-Null
    }
}

if ($Unregister) {
    Remove-WeeklyTask $taskFriday
    Remove-WeeklyTask $taskCatchUp
    Remove-WeeklyTask $taskLogon
    Write-Host "Unregister complete."
    exit 0
}

$createFri = @(
    "/Create", "/F",
    "/TN", $taskFriday,
    "/TR", $tr,
    "/SC", "WEEKLY",
    "/D", "FRI",
    "/ST", $At,
    "/RL", "LIMITED"
)
& schtasks.exe @createFri
if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks failed creating $taskFriday (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}
Write-Host "Registered: $taskFriday (Friday at $At)"

if ($PreferLogon) {
    $createLogon = @(
        "/Create", "/F",
        "/TN", $taskLogon,
        "/TR", $tr,
        "/SC", "ONLOGON",
        "/RL", "LIMITED"
    )
    & schtasks.exe @createLogon
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "ONLOGON failed (often needs Admin). Falling back to daily catch-up."
        $PreferLogon = $false
    }
    else {
        Write-Host "Registered: $taskLogon (At log on)"
    }
}

if (-not $PreferLogon) {
    $createCatch = @(
        "/Create", "/F",
        "/TN", $taskCatchUp,
        "/TR", $tr,
        "/SC", "DAILY",
        "/ST", $CatchUpAt,
        "/RL", "LIMITED"
    )
    & schtasks.exe @createCatch
    if ($LASTEXITCODE -ne 0) {
        Write-Error "schtasks failed creating $taskCatchUp (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    Write-Host "Registered: $taskCatchUp (daily at $CatchUpAt; no-ops when marker present)"
}

try {
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew
    $names = @($taskFriday, $taskCatchUp, $taskLogon)
    foreach ($name in $names) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            Set-ScheduledTask -TaskName $name -Settings $settings | Out-Null
        }
    }
}
catch {
    Write-Host "Note: could not tweak task settings via CIM ($($_.Exception.Message))"
}

Write-Host ""
Write-Host "Verify:"
Write-Host "  Get-ScheduledTask -TaskName 'LateTrainQueries-WeeklyOps-*'"
Write-Host "  Start-ScheduledTask -TaskName '$taskFriday'"
Write-Host "  python -m trainline --weekly-status"
Write-Host ""
Write-Host "Unregister later:"
Write-Host "  .\scripts\register-weekly-ops-task.ps1 -Unregister"
