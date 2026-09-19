# Native Windows soak / fault matrix driver for #140 (WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2).
# Executes the lifecycle, process-ownership and persistence scenarios against the real
# launcher + snapshot API + built frontend. Runtime smoke, not a unit test.
# Usage: powershell -ExecutionPolicy Bypass -File launcher/tests/windows_soak_uat_v2.ps1

param(
    [string]$Python = $env:CROSS_ASSET_PYTHON,
    [string]$ArtifactRoot = 'artifacts/windows_uat_v2'
)

$ErrorActionPreference = 'Stop'
# Local loopback health checks must never be routed through a system/registry proxy.
[System.Net.WebRequest]::DefaultWebProxy = $null
$Here = $PSScriptRoot
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $Here '..\..'))
$Launcher = Join-Path $Here '..\launcher.ps1'
$Stopper = Join-Path $Here '..\stop.ps1'
$CensusDriver = Join-Path $Here 'environment_census.py'
$ArtifactRootPath = if ([System.IO.Path]::IsPathRooted($ArtifactRoot)) {
    [System.IO.Path]::GetFullPath($ArtifactRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $ArtifactRoot))
}
$RuntimeDir = Join-Path (Split-Path $Launcher -Parent) '.runtime'
$PidFile = Join-Path $RuntimeDir 'servers.pid'
$AppUrl = 'http://127.0.0.1:8765'
$BackendUrl = 'http://127.0.0.1:8008'
$FrontendPort = 8765
$BackendPort = 8008
$RealSnapshotRoot = Join-Path $ArtifactRootPath 'dashboard_snapshots'
$ToolsNode = Join-Path $RepoRoot 'tools\node'

New-Item -ItemType Directory -Force -Path $ArtifactRootPath | Out-Null

if ([string]::IsNullOrWhiteSpace($Python)) {
    $VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) { $Python = $VenvPython }
}
if ([string]::IsNullOrWhiteSpace($Python) -or -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($PythonCmd) { $Python = $PythonCmd.Source }
}
if ([string]::IsNullOrWhiteSpace($Python)) { throw 'Python 3 runtime not found.' }
$env:CROSS_ASSET_PYTHON = $Python
# Real persisted snapshot root + user-space Node must be visible to the launcher.
$env:MACRO_WORKBENCH_SNAPSHOT_ROOT = $RealSnapshotRoot
$env:MACRO_WORKBENCH_NO_BROWSER = '1'
if (Test-Path -LiteralPath $ToolsNode -PathType Container) {
    $env:Path = "$ToolsNode;$env:Path"
}

$Soak = New-Object System.Collections.Generic.List[object]
$Ownership = New-Object System.Collections.Generic.List[object]
$Blockers = New-Object System.Collections.Generic.List[object]
$Sentinels = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ForeignProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ExpectedSnapshotId = $null
$ExpectedHistoryTechnical = $null
$ExpectedHistoryCanonical = $null

function Write-JsonFile([string]$Path, [object]$Payload) {
    $Payload | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Log-Progress([string]$Message) {
    $line = "{0} {1}" -f (Get-Date).ToString('HH:mm:ss.fff'), $Message
    Write-Host $line
    try { Add-Content -LiteralPath (Join-Path $ArtifactRootPath 'soak_progress.log') -Value $line -Encoding UTF8 } catch { }
}

function Port-Owners([int]$Port) {
    $rows = @()
    try {
        foreach ($conn in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)) {
            $pidValue = [int]$conn.OwningProcess
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
            $cmd = [string]$process.CommandLine
            $rows += [pscustomobject]@{
                port = $Port
                pid = $pidValue
                name = if ($process) { [string]$process.Name } else { $null }
                command_line = $cmd.Substring(0, [Math]::Min(240, $cmd.Length))
            }
        }
    } catch { }
    return @($rows)
}

function Read-PidMetadata {
    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) { return $null }
    try { return (Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

function Url-Result([string]$Uri, [int]$TimeoutSec = 6) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSec
        return [pscustomobject]@{ status = [int]$response.StatusCode; body = [string]$response.Content; error = $null }
    } catch {
        $status = -1
        if ($_.Exception.Response) { try { $status = [int]$_.Exception.Response.StatusCode } catch { } }
        return [pscustomobject]@{ status = $status; body = $null; error = $_.Exception.Message }
    }
}

function Json-Url([string]$Uri) {
    $result = Url-Result $Uri
    $json = $null
    if ($result.status -ge 200 -and $result.status -lt 300 -and $result.body) {
        try { $json = $result.body | ConvertFrom-Json } catch { }
    }
    return [pscustomobject]@{ status = $result.status; json = $json; error = $result.error }
}

function Snapshot-State {
    Log-Progress '  ss:health'
    $health = Json-Url "$AppUrl/api/health"
    Log-Progress '  ss:latest'
    $latest = Json-Url "$AppUrl/api/snapshot/latest"
    Log-Progress '  ss:history'
    $history = Json-Url "$AppUrl/api/snapshots"
    Log-Progress '  ss:done'
    $snapshotId = $null
    $runId = $null
    if ($latest.json) {
        $snapshotId = $latest.json.metadata.snapshot_id
        $runId = $latest.json.metadata.run_id
    }
    $technicalCount = $null
    $canonicalCount = $null
    if ($history.json) {
        $technicalCount = $history.json.technical_snapshot_count
        $canonicalCount = $history.json.canonical_week_count
        if ($null -eq $canonicalCount -and $history.json.history) { $canonicalCount = @($history.json.history).Count }
    }
    return [pscustomobject]@{
        health_status = $health.status
        latest_status = $latest.status
        history_status = $history.status
        snapshot_id = $snapshotId
        run_id = $runId
        technical_history_count = $technicalCount
        canonical_history_count = $canonicalCount
        pids = (Read-PidMetadata)
    }
}

function Record-Scenario(
    [string]$Scenario,
    [bool]$Pass,
    [string]$Detail,
    [string]$Category = 'LIFECYCLE',
    [object]$Before = $null,
    [object]$After = $null
) {
    $row = [pscustomobject]@{
        scenario = $Scenario
        category = $Category
        pass = $Pass
        detail = $Detail
        timestamp = (Get-Date).ToString('o')
        before = $Before
        after = $After
    }
    $Soak.Add($row)
    if ($Category -eq 'PROCESS_OWNERSHIP') { $Ownership.Add($row) }
    if ($Pass) { Write-Host "PASS [$Scenario] $Detail" -ForegroundColor Green }
    else {
        Write-Host "FAIL [$Scenario] $Detail" -ForegroundColor Red
        $Blockers.Add([pscustomobject]@{ class = 'NATIVE_WINDOWS_UAT_FAILURE'; scenario = $Scenario; detail = $Detail })
    }
}

function Invoke-LauncherCode {
    Log-Progress '  launcher:begin'
    # Start-Process -Wait waits for process exit only. A pipeline `& powershell | Out-Null`
    # would also wait for stdout EOF, which the launcher's redirected grandchildren keep open.
    # NOTE: Start-Process -Wait waits for the whole descendant tree (backend/frontend run
    # forever), so poll HasExited to wait for the launcher process itself only.
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$Launcher`"") -WindowStyle Hidden -PassThru
    while (-not $proc.HasExited) { Start-Sleep -Milliseconds 250 }
    Log-Progress '  launcher:end'
    return $proc.ExitCode
}

function Invoke-StopCode {
    Log-Progress '  stop:begin'
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$Stopper`"") -WindowStyle Hidden -PassThru
    while (-not $proc.HasExited) { Start-Sleep -Milliseconds 250 }
    Log-Progress '  stop:end'
    return $proc.ExitCode
}

function Wait-PortDown([int]$Port, [int]$Seconds = 8) {
    for ($i = 0; $i -lt ($Seconds * 4); $i++) {
        if (@(Port-Owners $Port).Count -eq 0) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Start-Sentinel([string]$Kind) {
    # Python console apps mangle -c args under Start-Process on some setups; use a script file.
    if ($Kind -eq 'python') {
        $scriptPath = Join-Path $ArtifactRootPath 'sentinel_task.py'
        if (-not (Test-Path -LiteralPath $scriptPath)) {
            Set-Content -LiteralPath $scriptPath -Value "import time`n`ntime.sleep(1800)`n" -Encoding ASCII
        }
        $p = Start-Process -FilePath $Python -ArgumentList "`"$scriptPath`"" -WindowStyle Hidden -PassThru
    } else {
        $nodeExe = Join-Path $ToolsNode 'node.exe'
        if (-not (Test-Path -LiteralPath $nodeExe)) {
            $nodeCmd = Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $nodeCmd) { return $null }
            $nodeExe = $nodeCmd.Source
        }
        $p = Start-Process -FilePath $nodeExe -ArgumentList '-e', 'setTimeout(()=>{},1800000)' -WindowStyle Hidden -PassThru
    }
    Start-Sleep -Milliseconds 700
    if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { return $null }
    $Sentinels.Add($p)
    return $p
}

function Sentinel-Alive([System.Diagnostics.Process]$Process) {
    if ($null -eq $Process) { return $null }
    return [bool](Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)
}

function Start-ForeignPort([int]$Port) {
    $p = Start-Process -FilePath $Python -ArgumentList @('-m', 'http.server', "$Port", '--bind', '127.0.0.1') -WorkingDirectory $ArtifactRootPath -WindowStyle Hidden -PassThru
    $ForeignProcesses.Add($p)
    for ($i = 0; $i -lt 20; $i++) {
        if (@(Port-Owners $Port).Count -gt 0) { break }
        Start-Sleep -Milliseconds 250
    }
    return $p
}

function Stop-HarnessProcess([System.Diagnostics.Process]$Process) {
    if ($null -ne $Process) {
        try { Stop-Process -Id $Process.Id -Force -ErrorAction Stop } catch { }
    }
}

function Get-OwnedBackendPid {
    $meta = Read-PidMetadata
    if ($null -eq $meta -or $null -eq $meta.backend) { return $null }
    return [int]$meta.backend.pid
}

function Get-OwnedFrontendPid {
    $meta = Read-PidMetadata
    if ($null -eq $meta -or $null -eq $meta.frontend) { return $null }
    return [int]$meta.frontend.pid
}

function Assert-Readback([string]$Scenario) {
    $state = Snapshot-State
    $countsOk = $true
    if ($ExpectedHistoryTechnical -ne $null -and $ExpectedHistoryCanonical -ne $null) {
        $countsOk = ($state.technical_history_count -eq $ExpectedHistoryTechnical) -and
            ($state.canonical_history_count -eq $ExpectedHistoryCanonical)
    }
    $ok = ($state.snapshot_id -eq $ExpectedSnapshotId) -and $countsOk
    Record-Scenario $Scenario $ok ("snapshot_id=$($state.snapshot_id) tech=$($state.technical_history_count) canonical=$($state.canonical_history_count) (expected snapshot_id=$ExpectedSnapshotId tech=$ExpectedHistoryTechnical canonical=$ExpectedHistoryCanonical)") 'PERSISTENCE' $null $state
    return $ok
}

function Resolve-BrowserExecutable {
    foreach ($name in @('msedge.exe', 'msedge', 'chrome.exe', 'chrome')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    foreach ($candidate in @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
     )) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    return $null
}

function Browser-Dom-Check([string]$ExpectedRunId) {
    $browser = Resolve-BrowserExecutable
    if (-not $browser) {
        return [pscustomobject]@{ attempted = $false; pass = $false; browser = $null; detail = 'Edge/Chrome executable not found for automated browser readback' }
    }
    $profile = Join-Path $ArtifactRootPath ('browser-profile-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $profile | Out-Null
    try {
        $argsBrowser = @(
            '--headless=new', '--disable-gpu', '--no-first-run', '--disable-default-apps',
            "--user-data-dir=$profile", '--virtual-time-budget=8000', '--dump-dom', $AppUrl
        )
        # Headless Edge/Chrome writes benign logs to stderr; with ErrorActionPreference=Stop
        # a 2>&1 redirect turns the first log line into a terminating error. Dampen it.
        $previousEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { $dom = (& $browser @argsBrowser 2>&1 | Out-String) } finally { $ErrorActionPreference = $previousEap }
        $hasRun = (-not [string]::IsNullOrWhiteSpace($ExpectedRunId)) -and ($dom.IndexOf($ExpectedRunId, [StringComparison]::OrdinalIgnoreCase) -ge 0)
        $noDemo = $dom.IndexOf('DEMO / GOLDEN', [StringComparison]::OrdinalIgnoreCase) -lt 0
        $available = $dom.IndexOf('snapshot-unavailable', [StringComparison]::OrdinalIgnoreCase) -lt 0
        $pass = $hasRun -and $noDemo -and $available
        $path = Join-Path $ArtifactRootPath 'BROWSER_DOM.html'
        Set-Content -LiteralPath $path -Value $dom -Encoding UTF8
        return [pscustomobject]@{
            attempted = $true
            pass = $pass
            browser = $browser
            has_expected_run_id = $hasRun
            no_demo_badge = $noDemo
            no_unavailable_state = $available
            detail = "run_id_found=$hasRun no_demo=$noDemo available=$available"
        }
    } finally {
        Remove-Item -LiteralPath $profile -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "=== WINDOWS SOAK / FAULT MATRIX V2 (#140) ==="
Write-Host "repo=$RepoRoot python=$Python snapshot_root=$RealSnapshotRoot"

# Regenerate environment census from the same harness.
& $Python $CensusDriver --artifact-root $ArtifactRoot | Out-Null

# --- Baseline: ensure stack stopped, then establish expected persisted identity. ---
[void](Invoke-StopCode)
$state0 = Snapshot-State
if ($state0.snapshot_id) {
    $ExpectedSnapshotId = $state0.snapshot_id
    $ExpectedHistoryTechnical = $state0.technical_history_count
    $ExpectedHistoryCanonical = $state0.canonical_history_count
} else {
    # Fall back to the persisted snapshot dir produced by real_snapshot_uat_v2.py.
    $latestFile = Join-Path $RealSnapshotRoot 'latest.json'
    if (Test-Path -LiteralPath $latestFile) {
        $doc = Get-Content -LiteralPath $latestFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $ExpectedSnapshotId = $doc.metadata.snapshot_id
    }
}
if ([string]::IsNullOrWhiteSpace($ExpectedSnapshotId)) {
    throw 'No persisted snapshot identity found; run real_snapshot_uat_v2.py first.'
}
Write-Host "Expected persisted snapshot_id=$ExpectedSnapshotId"

# Sentinels must survive every scenario (no global Python/Node kill).
$sentinelPy = Start-Sentinel 'python'
$sentinelNode = Start-Sentinel 'node'
Write-Host "Sentinels: python=$(if ($sentinelPy) { $sentinelPy.Id } else { 'n/a' }) node=$(if ($sentinelNode) { $sentinelNode.Id } else { 'n/a' })"

# --- S01 clean start (from fully stopped state). ---
Log-Progress 'S01'
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$ok = ($exitCode -eq 0) -and ($state.health_status -eq 200) -and ($state.latest_status -eq 200) -and ($state.pids -ne $null)
Record-Scenario 'S01-clean-start' $ok "exit=$exitCode health=$($state.health_status) latest=$($state.latest_status) backend=$(Get-OwnedBackendPid) frontend=$(Get-OwnedFrontendPid)" 'LIFECYCLE' $state0 $state
if ($ExpectedHistoryTechnical -eq $null -and $state.technical_history_count -ne $null) {
    # First healthy readback defines the persisted-history baseline (baseline stop leaves no
    # running API, so counts cannot be read before S01).
    $ExpectedHistoryTechnical = $state.technical_history_count
    $ExpectedHistoryCanonical = $state.canonical_history_count
    Write-Host "Expected persisted history counts: tech=$ExpectedHistoryTechnical canonical=$ExpectedHistoryCanonical"
}

# --- S02 warm start (deps/dist present: no rebuild needed). ---
Log-Progress 'S02'
$before = $state
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$ok = ($exitCode -eq 0) -and ($state.health_status -eq 200) -and ($state.snapshot_id -eq $ExpectedSnapshotId)
Record-Scenario 'S02-warm-start' $ok "exit=$exitCode health=$($state.health_status) snapshot_id=$($state.snapshot_id)" 'LIFECYCLE' $before $state

# --- S03 duplicate start (deterministic reuse, single stack). ---
Log-Progress 'S03'
$before = $state
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$sameBackend = (Get-OwnedBackendPid) -eq $before.pids.backend.pid
$sameFrontend = (Get-OwnedFrontendPid) -eq $before.pids.frontend.pid
$ok = ($exitCode -eq 0) -and $sameBackend -and $sameFrontend
Record-Scenario 'S03-duplicate-start-reuse' $ok "exit=$exitCode backend_unchanged=$sameBackend frontend_unchanged=$sameFrontend" 'PROCESS_OWNERSHIP' $before $state

# --- S04 API-only crash + recovery. ---
Log-Progress 'S04'
$before = $state
$backendPid = Get-OwnedBackendPid
try { Stop-Process -Id $backendPid -Force -ErrorAction Stop } catch { }
Start-Sleep -Seconds 1
$crashProxy = (Url-Result "$AppUrl/api/health").status   # proxy must answer 502, frontend stays up
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$ok = ($crashProxy -eq 502) -and ($exitCode -eq 0) -and ($state.health_status -eq 200) -and ($state.snapshot_id -eq $ExpectedSnapshotId)
Record-Scenario 'S04-api-crash-actionable-and-recovery' $ok "proxy_during_crash=$crashProxy recovery_exit=$exitCode health=$($state.health_status) snapshot_id=$($state.snapshot_id)" 'LIFECYCLE' $before $state
[void](Assert-Readback 'S05-api-crash-readback')

# --- S06 frontend-only crash + recovery. ---
Log-Progress 'S06'
$before = Snapshot-State
$frontendPid = Get-OwnedFrontendPid
try { Stop-Process -Id $frontendPid -Force -ErrorAction Stop } catch { }
Start-Sleep -Seconds 1
$frontDown = (Url-Result "$AppUrl/__health").status
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$ok = ($frontDown -eq -1) -and ($exitCode -eq 0) -and ($state.health_status -eq 200) -and ($state.snapshot_id -eq $ExpectedSnapshotId)
Record-Scenario 'S06-frontend-crash-and-recovery' $ok "frontend_during_crash=$frontDown recovery_exit=$exitCode health=$($state.health_status)" 'LIFECYCLE' $before $state

# --- S07 full stack restart via STOP + START. ---
Log-Progress 'S07'
$before = Snapshot-State
$stopExit = Invoke-StopCode
$portsDown = (Wait-PortDown $FrontendPort 8) -and (Wait-PortDown $BackendPort 8)
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$ok = ($stopExit -eq 0) -and $portsDown -and ($exitCode -eq 0) -and ($state.snapshot_id -eq $ExpectedSnapshotId)
Record-Scenario 'S07-full-restart' $ok "stop=$stopExit ports_down=$portsDown start=$exitCode snapshot_id=$($state.snapshot_id)" 'LIFECYCLE' $before $state
[void](Assert-Readback 'S08-full-restart-readback')

# --- S09 stale PID metadata (fake pids, no live stack). ---
Log-Progress 'S09'
[void](Invoke-StopCode)
$stale = [ordered]@{
    created_at = (Get-Date).ToString('o')
    repo_root = $RepoRoot
    frontend = @{ pid = 999981; port = $FrontendPort; host = '127.0.0.1'; script = 'C:\nonexistent\server.mjs' }
    backend = @{ pid = 999982; port = $BackendPort; host = '127.0.0.1'; module = 'decision_support.snapshot_cli serve'; snapshot_root = $RealSnapshotRoot }
}
$stale | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PidFile -Encoding UTF8
$before = Snapshot-State
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$ok = ($exitCode -eq 0) -and ($state.health_status -eq 200) -and ((Get-OwnedBackendPid) -ne 999982)
Record-Scenario 'S09-stale-pid-metadata' $ok "exit=$exitCode health=$($state.health_status) new_backend=$(Get-OwnedBackendPid)" 'PROCESS_OWNERSHIP' $before $state

# --- S10 foreign frontend port occupant fails closed and survives. ---
Log-Progress 'S10'
[void](Invoke-StopCode)
$before = Snapshot-State
$foreign = Start-ForeignPort $FrontendPort
$exitCode = Invoke-LauncherCode
$foreignAlive = [bool](Get-Process -Id $foreign.Id -ErrorAction SilentlyContinue)
$stackNotStarted = ($null -eq (Read-PidMetadata))
Record-Scenario 'S10-foreign-frontend-port-failclosed' (($exitCode -eq 13) -and $foreignAlive -and $stackNotStarted) "exit=$exitCode foreign_alive=$foreignAlive pid_file_absent=$stackNotStarted" 'PROCESS_OWNERSHIP' $before $null
Stop-HarnessProcess $foreign
[void](Wait-PortDown $FrontendPort 8)

# --- S11 foreign backend port occupant fails closed and survives. ---
Log-Progress 'S11'
$foreign = Start-ForeignPort $BackendPort
$exitCode = Invoke-LauncherCode
$foreignAlive = [bool](Get-Process -Id $foreign.Id -ErrorAction SilentlyContinue)
Record-Scenario 'S11-foreign-backend-port-failclosed' (($exitCode -eq 14) -and $foreignAlive) "exit=$exitCode foreign_alive=$foreignAlive" 'PROCESS_OWNERSHIP' $null $null
Stop-HarnessProcess $foreign
[void](Wait-PortDown $BackendPort 8)

# --- S12 corrupted runtime metadata while stack healthy: stop must refuse to kill. ---
Log-Progress 'S12'
$exitCode = Invoke-LauncherCode
$before = Snapshot-State
$savedMeta = Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8
Set-Content -LiteralPath $PidFile -Value '{ this is not json !!!' -Encoding UTF8
$stopExit = Invoke-StopCode
$stillHealthy = (Url-Result "$BackendUrl/api/health").status
$portsStillUp = (@(Port-Owners $BackendPort).Count -gt 0) -and (@(Port-Owners $FrontendPort).Count -gt 0)
$ok = ($stopExit -eq 43) -and ($stillHealthy -eq 200) -and $portsStillUp
Record-Scenario 'S12-corrupted-metadata-stop-refuses' $ok "stop=$stopExit backend_health=$stillHealthy ports_still_up=$portsStillUp" 'PROCESS_OWNERSHIP' $before $null
# Restore the exact saved metadata, then a normal stop must succeed.
Set-Content -LiteralPath $PidFile -Value $savedMeta -Encoding UTF8
$stopExit = Invoke-StopCode
$portsDown = (Wait-PortDown $FrontendPort 8) -and (Wait-PortDown $BackendPort 8)
Record-Scenario 'S13-restored-metadata-stop-succeeds' (($stopExit -eq 0) -and $portsDown) "stop=$stopExit ports_down=$portsDown" 'PROCESS_OWNERSHIP' $null $null

# --- S14 missing runtime metadata while health responds: stop refuses. ---
Log-Progress 'S14'
$exitCode = Invoke-LauncherCode
$backendPid = Get-OwnedBackendPid
$frontendPid = Get-OwnedFrontendPid
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
$stopExit = Invoke-StopCode
$stillHealthy = (Url-Result "$BackendUrl/api/health").status
$portsStillUp = (@(Port-Owners $BackendPort).Count -gt 0) -and (@(Port-Owners $FrontendPort).Count -gt 0)
$ok = ($stopExit -eq 41) -and ($stillHealthy -eq 200) -and $portsStillUp
Record-Scenario 'S14-missing-metadata-stop-refuses' $ok "stop=$stopExit backend_health=$stillHealthy ports_still_up=$portsStillUp" 'PROCESS_OWNERSHIP' $null $null
# Harness-side cleanup of its own stack (NOT via stop.ps1): restore metadata then stop.
$meta = [ordered]@{
    created_at = (Get-Date).ToString('o')
    repo_root = $RepoRoot
    frontend = @{ pid = $frontendPid; port = $FrontendPort; host = '127.0.0.1'; script = (Join-Path (Split-Path $Launcher -Parent) 'server.mjs') }
    backend = @{ pid = $backendPid; port = $BackendPort; host = '127.0.0.1'; module = 'decision_support.snapshot_cli serve'; snapshot_root = $RealSnapshotRoot }
}
$meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PidFile -Encoding UTF8
$stopExit = Invoke-StopCode
[void](Wait-PortDown $FrontendPort 8)
[void](Wait-PortDown $BackendPort 8)
Record-Scenario 'S15-missing-metadata-harness-recovery' (($stopExit -eq 0)) "stop_after_metadata_restore=$stopExit" 'PROCESS_OWNERSHIP' $null $null

# --- S16 browser reopen: fresh browser session reads the same real snapshot. ---
Log-Progress 'S16'
$exitCode = Invoke-LauncherCode
$state = Snapshot-State
$browser = Browser-Dom-Check $state.run_id
$ok = ($exitCode -eq 0) -and ($browser.attempted -eq $true) -and ($browser.pass)
Record-Scenario 'S16-browser-reopen' $ok ("exit=$exitCode browser=" + (Split-Path $browser.browser -Leaf) + ' ' + $browser.detail) 'LIFECYCLE' $null $state

# --- S17 final snapshot/history readback after the whole matrix. ---
Log-Progress 'S17'
[void](Assert-Readback 'S17-final-readback')

# --- Sentinels must have survived everything. ---
$pyAlive = Sentinel-Alive $sentinelPy
$nodeAlive = Sentinel-Alive $sentinelNode
$ok = ($pyAlive -ne $false) -and ($nodeAlive -ne $false)
Record-Scenario 'S18-unrelated-processes-survive' $ok "python_sentinel=$pyAlive node_sentinel=$nodeAlive" 'PROCESS_OWNERSHIP' $null $null

# --- Harness cleanup: stop owned stack, then sentinels/foreign leftovers. ---
$finalStop = Invoke-StopCode
foreach ($s in $Sentinels) { Stop-HarnessProcess $s }
foreach ($f in $ForeignProcesses) { Stop-HarnessProcess $f }

$passed = @($Soak | Where-Object { $_.pass }).Count
$total = $Soak.Count
$summary = [ordered]@{
    contract = 'WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2'
    generated_at = (Get-Date).ToString('o')
    expected_snapshot_id = $ExpectedSnapshotId
    expected_technical_history_count = $ExpectedHistoryTechnical
    expected_canonical_history_count = $ExpectedHistoryCanonical
    final_stop_exit = $finalStop
    total = $total
    passed = $passed
    failed = ($total - $passed)
    status = if ($passed -eq $total) { 'SOAK_PASS' } else { 'SOAK_FAIL' }
    scenarios = $Soak
}
Write-JsonFile (Join-Path $ArtifactRootPath 'SOAK_MATRIX.json') $summary

$ownSummary = [ordered]@{
    contract = 'WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2'
    generated_at = (Get-Date).ToString('o')
    invariants = @(
        'STOP/launcher own only command-line-verified launcher processes recorded in servers.pid',
        'foreign port occupants fail closed (exit 13/14) and always survive',
        'corrupted or missing runtime metadata never triggers a kill of unverified processes',
        'unrelated Python/Node processes survive every lifecycle scenario'
    )
    scenarios = $Ownership
}
Write-JsonFile (Join-Path $ArtifactRootPath 'PROCESS_OWNERSHIP_MATRIX.json') $ownSummary

$ledger = [ordered]@{
    contract = 'WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2'
    generated_at = (Get-Date).ToString('o')
    blockers = $Blockers
    status = if ($Blockers.Count -eq 0) { 'NO_OPEN_BLOCKERS_FROM_SOAK' } else { 'SOAK_BLOCKERS_PRESENT' }
}
Write-JsonFile (Join-Path $ArtifactRootPath 'BLOCKER_LEDGER.json') $ledger

function ConvertTo-MarkdownRows([System.Collections.Generic.List[object]]$Rows) {
    $lines = @()
    foreach ($r in $Rows) {
        $lines += ("| {0} | {1} | {2} |" -f $r.scenario, $(if ($r.pass) { 'PASS' } else { 'FAIL' }), ($r.detail -replace '\|', '/'))
    }
    return $lines
}

$md = @(
    '# Windows Soak / Fault Matrix V2 (#140)',
    '',
    "Generated: ``$($summary.generated_at)``",
    '',
    "- status: **$($summary.status)** ($passed/$total scenarios passed)",
    "- expected persisted snapshot_id: ``$ExpectedSnapshotId``",
    "- final stop exit: ``$finalStop``",
    '',
    '## Scenarios',
    '',
    '| scenario | result | detail |',
    '|---|---|---|'
) + (ConvertTo-MarkdownRows $Soak) + @(
    '',
    '## Process ownership invariants',
    '',
    ($ownSummary.invariants | ForEach-Object { "- $_" }),
    '',
    '## Blockers',
    '',
    $(if ($Blockers.Count -eq 0) { '- none' } else { $Blockers | ForEach-Object { "- [$($_.scenario)] $($_.detail)" } }),
    ''
)
Set-Content -LiteralPath (Join-Path $ArtifactRootPath 'SOAK_MATRIX.md') -Value $md -Encoding UTF8

$ownMd = @(
    '# Process Ownership Matrix (#140)',
    '',
    "Generated: ``$($ownSummary.generated_at)``",
    '',
    '## Invariants',
    '',
    ($ownSummary.invariants | ForEach-Object { "- $_" }),
    '',
    '| scenario | result | detail |',
    '|---|---|---|'
) + (ConvertTo-MarkdownRows $Ownership) + @('')
Set-Content -LiteralPath (Join-Path $ArtifactRootPath 'PROCESS_OWNERSHIP_MATRIX.md') -Value $ownMd -Encoding UTF8

$ledgerMd = @(
    '# Blocker Ledger (#140 native soak)',
    '',
    "Generated: ``$($ledger.generated_at)``",
    '',
    "status: **$($ledger.status)**",
    '',
    $(if ($Blockers.Count -eq 0) { '- none' } else { $Blockers | ForEach-Object { "- [$($_.scenario)] $($_.detail)" } }),
    ''
)
Set-Content -LiteralPath (Join-Path $ArtifactRootPath 'BLOCKER_LEDGER.md') -Value $ledgerMd -Encoding UTF8

Write-Host ''
Write-Host "==== SOAK SUMMARY: $($summary.status) ($passed/$total) ===="
$Soak | ForEach-Object { "{0} {1} {2}" -f $(if ($_.pass) { 'PASS' } else { 'FAIL' }), $_.scenario, $_.detail } | Write-Host
exit $(if ($passed -eq $total) { 0 } else { 1 })
