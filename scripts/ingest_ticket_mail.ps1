<#
.SYNOPSIS
  Daily Gmail ticket-photo drain into tickets/unclassified (Epic 8).
#>
[CmdletBinding()]
param(
    [string] $ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
Set-Location -LiteralPath $ProjectRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "python not found on PATH"
    exit 2
}

$creds = Join-Path $ProjectRoot "creds\trainConfig.txt"
if (Test-Path -LiteralPath $creds) {
    $env:HSP_CREDENTIALS_FILE = (Resolve-Path -LiteralPath $creds).Path
}

$ca = Join-Path $ProjectRoot "creds\ca-bundle.pem"
if (Test-Path -LiteralPath $ca) {
    $caPath = (Resolve-Path -LiteralPath $ca).Path
    $env:REQUESTS_CA_BUNDLE = $caPath
    $env:SSL_CERT_FILE = $caPath
    $env:CURL_CA_BUNDLE = $caPath
}

$logDir = Join-Path $ProjectRoot "Results\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logDir "ingest-ticket-mail-$stamp.log"

Write-Host "[ingest_ticket_mail] Running: python -m trainline --ingest-ticket-mail"
Write-Host "[ingest_ticket_mail] Log: $logFile"

# Do not pipe stderr into the PowerShell error stream — CLI progress is on
# stderr and would abort under $ErrorActionPreference = Stop.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
cmd /c "`"$($python.Source)`" -m trainline --ingest-ticket-mail > `"$logFile`" 2>&1"
$rc = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if (Test-Path -LiteralPath $logFile) {
    Get-Content -LiteralPath $logFile | Write-Host
    Add-Content -LiteralPath $logFile -Value "`nEXIT_CODE=$rc"
}
exit $rc
