<#
.SYNOPSIS
  Weekly Delay Repay ops entrypoint for Windows Task Scheduler (FR32, NFR12).

.DESCRIPTION
  Sets AVG/HSP env, skips when the anchor-Friday marker is already present,
  then runs ``python -m trainline --weekly-ops``.

  Register with:  .\scripts\register-weekly-ops-task.ps1

.PARAMETER ProjectRoot
  Repo root (default: parent of scripts/).

.PARAMETER LiveSubmit
  Pass --live-submit through (attended captcha). Default is FakeBrowser dry file.

.PARAMETER Force
  Pass --weekly-ops-force to ignore an existing completion marker.
#>
[CmdletBinding()]
param(
    [string] $ProjectRoot = "",
    [switch] $LiveSubmit,
    [switch] $Force
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
Set-Location -LiteralPath $ProjectRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "python not found on PATH. Activate your venv or install Python."
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
    $env:NODE_EXTRA_CA_CERTS = $caPath
}

$argv = @("-m", "trainline", "--weekly-ops")
if ($LiveSubmit) { $argv += "--live-submit" }
if ($Force) { $argv += "--weekly-ops-force" }

Write-Host "[weekly_ops] ProjectRoot=$ProjectRoot"
Write-Host "[weekly_ops] Running: python $($argv -join ' ')"
& python @argv
exit $LASTEXITCODE
