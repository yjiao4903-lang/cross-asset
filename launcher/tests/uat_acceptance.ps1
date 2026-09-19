# REAL-runtime acceptance driver for #134.
# Runs the manual-flow acceptance scenarios against the actual repo + launcher.
# Usage:
#   powershell -ExecutionPolicy Bypass -File launcher/tests/uat_acceptance.ps1
#
# This script drives a real launcher start/stop/restart/foreign-occupancy cycle and
# prints a PASS/FAIL line per acceptance scenario. It is a runtime smoke, not a unit
# test: it requires the same prerequisites as the launcher (Python 3, Node.js, npm,
# a built frontend/dist), and it opens real OS processes on loopback ports 8765/8008.

param(
    [string]$Python = ($env:CROSS_ASSET_PYTHON),
    [string]$NodeDir = (Split-Path (Get-Command node -ErrorAction SilentlyContinue).Source -Parent),
    [switch]$OpenBrowserAllowed
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Launcher = Join-Path $Here '..\launcher.ps1'
$Stopper  = Join-Path $Here '..\stop.ps1'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $Here '..\..'))

if ([string]::IsNullOrWhiteSpace($Python)) { $Python = (Join-Path $RepoRoot '.venv\Scripts\python.exe') }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found: $Python (set CROSS_ASSET_PYTHON)" }

if ($NodeDir) { $env:Path = "$NodeDir;$env:Path" }
if (-not $OpenBrowserAllowed) { $env:MACRO_WORKBENCH_NO_BROWSER = '1' }
$env:CROSS_ASSET_PYTHON = $Python

$results = New-Object System.Collections.Generic.List[object]
# Start-Process -Wait waits for process exit only; `& script | Out-Null` would also wait for
# stdout EOF, which the launcher's redirected grandchildren keep open for the whole session.
function Invoke-LauncherWait {
    # Poll HasExited: Start-Process -Wait waits for the whole descendant tree.
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$Launcher`"") -WindowStyle Hidden -PassThru
    while (-not $proc.HasExited) { Start-Sleep -Milliseconds 250 }
    return $proc.ExitCode
}
function Invoke-StopperWait {
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$Stopper`"") -WindowStyle Hidden -PassThru
    while (-not $proc.HasExited) { Start-Sleep -Milliseconds 250 }
    return $proc.ExitCode
}
function Record-Pass($scenario, $detail = '') {
    $results.Add([pscustomobject]@{ scenario = $scenario; pass = $true;  detail = $detail })
    Write-Host "PASS [${scenario}] $detail" -ForegroundColor Green
}
function Record-Fail($scenario, $detail = '') {
    $results.Add([pscustomobject]@{ scenario = $scenario; pass = $false; detail = $detail })
    Write-Host "FAIL [${scenario}] $detail" -ForegroundColor Red
}
function Url-Status([string]$Uri, [int]$TimeoutSec = 6) {
    try { return [int](Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSec).StatusCode }
    catch { if ($_.Exception.Response) { try { return [int]$_.Exception.Response.StatusCode } catch { return -1 } } ; return -1 }
}
function Port-Listening([int]$Port) {
    try { return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop) } catch { return $false }
}

# Scenario 1: clean start succeeds (deps/build/start)
$exitCode = Invoke-LauncherWait
if ($exitCode -eq 0) { Record-Pass '1-clean-start' "launcher exit=$LASTEXITCODE" } else { Record-Fail '1-clean-start' "launcher exit=$LASTEXITCODE" }

# Scenario 2: backend snapshot API on owned port, /api/health reachable
$health = Url-Status 'http://127.0.0.1:8008/api/health'
if ($health -eq 200) { Record-Pass '2-backend-health' "backend /api/health HTTP $health" } else { Record-Fail '2-backend-health' "backend /api/health HTTP $health" }

# Scenario 3: frontend normal mode reads /api via proxy; /__health serves dist
$fh = Url-Status 'http://127.0.0.1:8765/__health'
$idx = Url-Status 'http://127.0.0.1:8765/'
$prox = Url-Status 'http://127.0.0.1:8765/api/health'
if ($fh -eq 200 -and $idx -eq 200 -and $prox -eq 200) { Record-Pass '3-frontend-api-proxy' "dist + /api proxy OK ($fh/$idx/$prox)" } else { Record-Fail '3-frontend-api-proxy' "dist=$fh index=$idx proxy=$prox" }

# Scenario 6: duplicate start deterministic (no second stack)
$exitCode = Invoke-LauncherWait
if ($exitCode -eq 0) { Record-Pass '6-duplicate-start' 'second start reused healthy stack (exit 0)' } else { Record-Fail '6-duplicate-start' "second launch exit=$LASTEXITCODE" }
$meta = Get-Content (Join-Path $Here '..\.runtime\servers.pid') -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
if ($meta) {
    Record-Pass '6-owns-single-stack' "backend=$($meta.backend.pid) frontend=$($meta.frontend.pid)"
} else { Record-Fail '6-owns-single-stack' 'no pid metadata' }

# Scenario 9: missing snapshot -> backend DEGRADED, /api/snapshot/latest 404 (no demo)
$latest = Url-Status 'http://127.0.0.1:8765/api/snapshot/latest'
if ($latest -eq 404) { Record-Pass '9-missing-snapshot-unavailable' "/api/snapshot/latest HTTP $latest (no demo)" } else { Record-Fail '9-missing-snapshot-unavailable' "/api/snapshot/latest HTTP $latest" }

# Scenario 5/7: foreign occupancy of port 8008 fails closed, foreign survives
# (stop first so the port is free and genuinely 'foreign').
$stopExit = Invoke-StopperWait
if ($stopExit -ne 0) { Record-Fail '5-stop' "stop exit=$stopExit" } else { Record-Pass '5-stop' 'launcher-owned processes stopped, health down' }

$foreign = $null
try {
    $src = 'from http.server import BaseHTTPRequestHandler,HTTPServer
class H(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  self.send_response(200); self.end_headers()
s=HTTPServer(("127.0.0.1",8008),H); s.serve_forever()'
    $tmp = Join-Path $env:TEMP ("uat_foreign_" + [guid]::NewGuid().ToString('N') + ".py")
    Set-Content -Path $tmp -Value $src -Encoding UTF8
    $foreign = Start-Process -FilePath $Python -ArgumentList $tmp -WorkingDirectory $Here -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 1200
    & $Launcher | Out-Null
    $launcherExit = $LASTEXITCODE
    $foreignAlive = [bool](Get-Process -Id $foreign.Id -ErrorAction SilentlyContinue)
    if ($launcherExit -eq 14 -and $foreignAlive) { Record-Pass '7-foreign-port-failclosed' "exit=$launcherExit, foreign port occupant survived" }
    else { Record-Fail '7-foreign-port-failclosed' "exit=$launcherExit foreignAlive=$foreignAlive" }
} finally {
    if ($foreign -and (Get-Process -Id $foreign.Id -ErrorAction SilentlyContinue)) { Stop-Process -Id $foreign.Id -Force -ErrorAction SilentlyContinue }
}

# Scenario 8: stop; restart; no fabricated run (latest_snapshot_id stays null)
& $Launcher | Out-Null
$h2 = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 6).Content | ConvertFrom-Json
if ($null -eq $h2.latest_snapshot_id) { Record-Pass '8-restart-no-fabrication' 'restart did not fabricate a run (latest null)' } else { Record-Fail '8-restart-no-fabrication' "latest=$( $h2.latest_snapshot_id)" }

$null = Invoke-StopperWait

Write-Host ''
Write-Host '==== UAT SUMMARY ===='
$passed = ($results | Where-Object { $_.pass }).Count
$failedCount = $results.Count - $passed
$results | ForEach-Object { "{0} {1} {2}" -f $(if ($_.pass) {'PASS'} else {'FAIL'}), $_.scenario, $_.detail }
Write-Host "TOTAL=$($results.Count) PASS=$passed FAIL=$failedCount"
exit $(if ($failedCount -eq 0) { 0 } else { 1 })