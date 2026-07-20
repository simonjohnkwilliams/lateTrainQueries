<#
.SYNOPSIS
  Register a once-daily Gmail ticket-photo ingest task (Epic 8.4 / NFR14).

.DESCRIPTION
  Creates LateTrainQueries-TicketIngest-Daily running --ingest-ticket-mail.
  Cadence locked 2026-07-20: once daily (not a 15-min poller). Friday
  --weekly-ops also ingests first.

.PARAMETER At
  Local time for the daily trigger (default 09:00 — before CatchUp 09:30).

.PARAMETER Unregister
  Remove the task.
#>
[CmdletBinding()]
param(
    [string] $At = "09:00",
    [string] $ProjectRoot = "",
    [switch] $Unregister
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$runner = Join-Path $ProjectRoot "scripts\ingest_ticket_mail.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    Write-Error "Missing runner: $runner"
    exit 2
}

$taskName = "LateTrainQueries-TicketIngest-Daily"
$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runner`""

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed task: $taskName"
    }
    else {
        schtasks.exe /Delete /F /TN $taskName 2>$null | Out-Null
        Write-Host "Task not found or removed: $taskName"
    }
    exit 0
}

& schtasks.exe /Create /F /TN $taskName /TR $tr /SC DAILY /ST $At /RL LIMITED
if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks failed creating $taskName (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}
Write-Host "Registered: $taskName (daily at $At)"
Write-Host "Verify:  Get-ScheduledTask -TaskName '$taskName'"
Write-Host "Manual:  Start-ScheduledTask -TaskName '$taskName'"
Write-Host "CLI:     python -m trainline --ingest-ticket-mail"
