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

Write-Host "[ingest_ticket_mail] Running: python -m trainline --ingest-ticket-mail"
& python -m trainline --ingest-ticket-mail
exit $LASTEXITCODE
