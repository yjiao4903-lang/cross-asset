param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path "data/raw", "data/db", "data/manual_inbox", "data/manual_archive", "artifacts" | Out-Null
if (-not $SkipInstall -and (Get-Command uv -ErrorAction SilentlyContinue)) { uv sync }
Write-Host "Cross-asset engine workspace initialized."

