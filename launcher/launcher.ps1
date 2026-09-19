[CmdletBinding()]
param(
    [int]$Port = 8765,
    [int]$BackendPort = 8008
)

$ErrorActionPreference = 'Stop'
$HostAddress = '127.0.0.1'
$AppUrl = "http://${HostAddress}:$Port"
$HealthUrl = "$AppUrl/__health"
$BackendHealthUrl = "http://${HostAddress}:${BackendPort}/api/health"
$ExpectedApp = 'macro-workbench'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$FrontendDir = Join-Path $RepoRoot 'frontend'
$PackageJson = Join-Path $FrontendDir 'package.json'
$PackageLock = Join-Path $FrontendDir 'package-lock.json'
$DistIndex = Join-Path $FrontendDir 'dist\index.html'
$RuntimeDir = Join-Path $PSScriptRoot '.runtime'
$LogsDir = Join-Path $PSScriptRoot 'logs'
$PidFile = Join-Path $RuntimeDir 'servers.pid'
$LauncherLog = Join-Path $LogsDir 'launcher.log'
$FrontendStdoutLog = Join-Path $RuntimeDir 'frontend-stdout.log'
$FrontendStderrLog = Join-Path $RuntimeDir 'frontend-stderr.log'
$BackendStdoutLog = Join-Path $RuntimeDir 'backend-stdout.log'
$BackendStderrLog = Join-Path $RuntimeDir 'backend-stderr.log'
$ServerScript = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'server.mjs'))
$DefaultSnapshotRoot = Join-Path $RepoRoot 'artifacts\dashboard_snapshots'
$SnapshotRoot = if ([string]::IsNullOrWhiteSpace($env:MACRO_WORKBENCH_SNAPSHOT_ROOT)) {
    [System.IO.Path]::GetFullPath($DefaultSnapshotRoot)
} else {
    [System.IO.Path]::GetFullPath($env:MACRO_WORKBENCH_SNAPSHOT_ROOT)
}
$MutexName = 'Local\CrossAssetWorkbenchLauncher'

# Locate a viable Python runtime: repo-local venv first, then PATH/canonical launcher.
function Resolve-Python {
    $venv = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venv -PathType Leaf) { return $venv }
    $envName = $env:CROSS_ASSET_PYTHON
    if (-not [string]::IsNullOrWhiteSpace($envName) -and (Test-Path -LiteralPath $envName -PathType Leaf)) { return $envName }
    foreach ($candidate in @('python', 'py')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $cmd) {
            if ($candidate -eq 'py') {
                # py launcher: prefer the first Python 3 interpreter.
                try {
                    $out = (& py -3 -c "import sys,os;print(os.path.abspath(sys.executable))" 2>&1 | Select-Object -First 1)
                    if ($LASTEXITCODE -eq 0 -and $out) { return $out }
                } catch { }
            }
            return $cmd.Source
        }
    }
    return $null
}

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogsDir | Out-Null

function Write-LauncherLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO','WARN','ERROR')][string]$Level = 'INFO'
    )
    $timestamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffK')
    $line = "$timestamp [$Level] $Message"
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding UTF8
    if ($Level -eq 'ERROR') { Write-Host $Message -ForegroundColor Red }
    elseif ($Level -eq 'WARN') { Write-Host $Message -ForegroundColor Yellow }
    else { Write-Host $Message }
}

function Test-TruthyEnv {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $false }
    return @('1','true','yes','on') -contains $value.Trim().ToLowerInvariant()
}

function Test-Url {
    param([string]$Uri, [int]$TimeoutSec = 1)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSec
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response) {
            try { return [int]$_.Exception.Response.StatusCode } catch { return $null }
        }
        return $null
    }
}

function Test-Health {
    $code = Test-Url -Uri $HealthUrl
    if ($null -eq $code -or $code -ne 200) { return $false }
    try {
        $payload = (Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 1).Content | ConvertFrom-Json
        return ($payload.status -eq 'ok' -and $payload.app -eq $ExpectedApp)
    } catch { return $false }
}

function Test-BackendHealth {
    $code = Test-Url -Uri $BackendHealthUrl
    if ($null -eq $code) { return $false }
    # /api/health returns 200 both when a snapshot exists (status OK) and when degraded (DEGRADED).
    return ($code -eq 200)
}

function Test-PortOpen {
    param([int]$PortNumber)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect($HostAddress, $PortNumber, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(350)) { return $false }
        $client.EndConnect($result)
        return $true
    } catch { return $false }
    finally { $client.Close() }
}

function Get-PidMetadata {
    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) { return $null }
    try { return (Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

# Ownership check: a PID is launcher-owned iff its command line references launcher scripts (server.mjs)
# or the snapshot_cli module AND it is recorded in our own metadata file.
function Test-OwnedProcess {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($null -eq $process) { return $false }
        $commandLine = [string]$process.CommandLine
        if ([string]::IsNullOrWhiteSpace($commandLine)) { return $false }
        $marks = @($ServerScript, 'decision_support.snapshot_cli')
        foreach ($mark in $marks) {
            if ($commandLine.IndexOf($mark, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
        }
        return $false
    } catch { return $false }
}

function Get-LiveOwnedPids {
    $meta = Get-PidMetadata
    if ($null -eq $meta) { return @() }
    $result = @()
    foreach ($entry in @($meta.backend, $meta.frontend)) {
        if ($null -eq $entry) { continue }
        $pidValue = 0
        if ([int]::TryParse([string]$entry.pid, [ref]$pidValue) -and (Test-OwnedProcess -ProcessId $pidValue)) {
            $result += $pidValue
        }
    }
    return @($result | Select-Object -Unique)
}

function Remove-StalePidMetadata {
    $meta = Get-PidMetadata
    if ($null -eq $meta) {
        # If the port still answers health without owned metadata, treat as foreign and leave it alone.
        if (Test-Health) { Write-LauncherLog 'Health responds but no ownership metadata exists. Not managing it.' 'WARN' }
        return
    }
    $live = Get-LiveOwnedPids
    if ($live.Count -eq 0) {
        Write-LauncherLog 'Removing stale PID metadata (no launcher-owned live process found).' 'WARN'
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Open-WorkbenchBrowser {
    if (Test-TruthyEnv 'MACRO_WORKBENCH_NO_BROWSER') {
        Write-LauncherLog "Browser open skipped by MACRO_WORKBENCH_NO_BROWSER; app URL: $AppUrl"
        return $true
    }
    try {
        Start-Process $AppUrl | Out-Null
        Write-LauncherLog "Opened default browser: $AppUrl"
        return $true
    } catch {
        Write-LauncherLog "Browser could not be opened automatically. Open $AppUrl manually. Error: $($_.Exception.Message)" 'WARN'
        return $false
    }
}

function Resolve-Executable {
    param([Parameter(Mandatory = $true)][string[]]$Names)
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) { return $command.Source }
    }
    return $null
}

function Invoke-NpmCommand {
    param(
        [Parameter(Mandatory = $true)][string]$NpmPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    Write-LauncherLog "$Label started: npm $($Arguments -join ' ')"
    $token = [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $RuntimeDir "npm-$token.out.log"
    $stderrPath = Join-Path $RuntimeDir "npm-$token.err.log"
    try {
        $process = Start-Process -FilePath $NpmPath -ArgumentList $Arguments -WorkingDirectory $FrontendDir `
            -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -Wait -PassThru
        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                Get-Content -LiteralPath $path -Encoding UTF8 | ForEach-Object {
                    Add-Content -LiteralPath $LauncherLog -Value $_ -Encoding UTF8
                    Write-Host $_
                }
            }
        }
        $exitCode = $process.ExitCode
    } finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
    if ($exitCode -ne 0) {
        Write-LauncherLog "$Label failed with exit code $exitCode." 'ERROR'
        return $exitCode
    }
    Write-LauncherLog "$Label completed successfully."
    return 0
}

function Test-DependenciesNeedInstall {
    $nodeModules = Join-Path $FrontendDir 'node_modules'
    if (-not (Test-Path -LiteralPath $nodeModules -PathType Container)) { return $true }
    if (Test-Path -LiteralPath $PackageLock -PathType Leaf) {
        $installStamp = Join-Path $nodeModules '.package-lock.json'
        if (-not (Test-Path -LiteralPath $installStamp -PathType Leaf)) { return $true }
        $lockTime = (Get-Item -LiteralPath $PackageLock).LastWriteTimeUtc
        $stampTime = (Get-Item -LiteralPath $installStamp).LastWriteTimeUtc
        if ($lockTime -gt $stampTime) { return $true }
    }
    return $false
}

function Get-BuildInputs {
    $paths = New-Object System.Collections.Generic.List[System.IO.FileInfo]
    $srcDir = Join-Path $FrontendDir 'src'
    if (Test-Path -LiteralPath $srcDir -PathType Container) {
        Get-ChildItem -LiteralPath $srcDir -File -Recurse | ForEach-Object { $paths.Add($_) }
    }
    foreach ($pattern in @('index.html', 'package.json', 'package-lock.json', 'vite.config.*')) {
        Get-ChildItem -Path (Join-Path $FrontendDir $pattern) -File -ErrorAction SilentlyContinue | ForEach-Object { $paths.Add($_) }
    }
    return $paths
}

function Test-BuildNeeded {
    if (-not (Test-Path -LiteralPath $DistIndex -PathType Leaf)) { return $true }
    $distTime = (Get-Item -LiteralPath $DistIndex).LastWriteTimeUtc
    foreach ($input in (Get-BuildInputs)) {
        if ($input.LastWriteTimeUtc -gt $distTime) { return $true }
    }
    return $false
}

function Wait-Backend {
    for ($i = 1; $i -le 40; $i++) {
        if (Test-BackendHealth) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Wait-Frontend {
    for ($i = 1; $i -le 30; $i++) {
        if (Test-Health) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-Backend {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (Test-PortOpen -PortNumber $BackendPort) {
        if (Test-BackendHealth) {
            Write-LauncherLog "Backend API already healthy on :${BackendPort}; reusing existing owned or prior instance is ONLY allowed when our metadata owns it."
            if ((Get-PidMetadata) -and (Test-OwnedProcessExists)) {
                Write-LauncherLog 'Existing healthy backend is launcher-owned; not starting a second one.'
                return $true
            }
            Write-LauncherLog "Backend port $BackendPort responds but is not verifiably launcher-owned. Refusing to attach to foreign process." 'ERROR'
            return $false
        }
        Write-LauncherLog "Backend port $BackendPort is occupied by another application. Macro Workbench was not started." 'ERROR'
        return $false
    }

    if (Test-Path -LiteralPath $BackendStdoutLog) { Remove-Item -LiteralPath $BackendStdoutLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $BackendStderrLog) { Remove-Item -LiteralPath $BackendStderrLog -Force -ErrorAction SilentlyContinue }

    $env:PYTHONPATH = if ($env:PYTHONPATH) { $env:PYTHONPATH } else { (Join-Path $RepoRoot 'src') }
    $quotedSnapshotRoot = '"' + $SnapshotRoot + '"'
    $argsBackend = @('-m', 'cross_asset.decision_support.snapshot_cli', 'serve',
        '--root', $quotedSnapshotRoot, '--host', $HostAddress, '--port', "$BackendPort")
    $process = Start-Process -FilePath $PythonPath -ArgumentList $argsBackend `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden `
        -RedirectStandardOutput $BackendStdoutLog -RedirectStandardError $BackendStderrLog -PassThru
    Write-LauncherLog "Backend API started (listener) with PID $($process.Id)."

    if (-not (Wait-Backend)) {
        Write-LauncherLog 'Backend API failed to become healthy within the launch window. Logs: backend-stderr.log' 'ERROR'
        try { Stop-Process -Id $process.Id -ErrorAction Stop } catch { }
        return $false
    }
    return $process.Id
}

function Test-OwnedProcessExists {
    $live = Get-LiveOwnedPids
    return ($live.Count -gt 0)
}

function Start-Frontend {
    param([Parameter(Mandatory = $true)][string]$NodePath)

    if (Test-Health) {
        Write-LauncherLog 'Duplicate start detected: existing healthy Macro Workbench server is launcher-owned.'
        return $null
    }

    if (Test-Path -LiteralPath $FrontendStdoutLog) { Remove-Item -LiteralPath $FrontendStdoutLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $FrontendStderrLog) { Remove-Item -LiteralPath $FrontendStderrLog -Force -ErrorAction SilentlyContinue }

    $process = Start-Process -FilePath $NodePath `
        -ArgumentList @("`"$ServerScript`"") `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $FrontendStdoutLog `
        -RedirectStandardError $FrontendStderrLog `
        -PassThru
    Write-LauncherLog "Frontend proxy started with PID $($process.Id)."
    if (-not (Wait-Frontend)) {
        Write-LauncherLog 'Frontend failed to become healthy within the launch window.' 'ERROR'
        try { Stop-Process -Id $process.Id -ErrorAction Stop } catch { }
        return $null
    }
    return $process.Id
}

function Write-PidMetadata {
    param([int]$BackendPid, [int]$FrontendPid)
    $meta = [ordered]@{
        created_at = (Get-Date).ToString('o')
        repo_root   = $RepoRoot
        frontend    = @{ pid = $FrontendPid; port = $Port; host = $HostAddress; script = $ServerScript }
        backend     = @{ pid = $BackendPid; port = $BackendPort; host = $HostAddress; module = 'decision_support.snapshot_cli serve'; snapshot_root = $SnapshotRoot }
    }
    $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $PidFile -Encoding UTF8
}

function Stop-OwnedStackForRecovery {
    $live = Get-LiveOwnedPids
    foreach ($procId in $live) {
        if (Test-OwnedProcess -ProcessId $procId) {
            try {
                Stop-Process -Id $procId -ErrorAction Stop
                try { Wait-Process -Id $procId -Timeout 5 -ErrorAction SilentlyContinue } catch { }
                Write-LauncherLog "Stopped launcher-owned partial-stack process PID $procId for deterministic recovery." 'WARN'
            } catch {
                Write-LauncherLog "Failed to stop launcher-owned partial-stack PID $($procId): $($_.Exception.Message)" 'ERROR'
                return $false
            }
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Test-PortOpen -PortNumber $Port) -and -not (Test-PortOpen -PortNumber $BackendPort)) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    Write-LauncherLog 'Owned partial stack was stopped but one or more ports remain occupied; refusing to kill any unverified process.' 'ERROR'
    return $false
}

function Invoke-LauncherMain {
    Write-LauncherLog "Launcher start. repo=$RepoRoot frontend=${HostAddress}:$Port backend=${HostAddress}:$BackendPort snapshot_root=$SnapshotRoot"

    $mutex = New-Object System.Threading.Mutex($false, $MutexName)
    $hasMutex = $false
    try {
        try { $hasMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $hasMutex = $true; Write-LauncherLog 'Recovered abandoned launcher mutex.' 'WARN' }

        if (-not $hasMutex) {
            Write-LauncherLog 'Another launcher process is active.' 'WARN'
            if (Wait-Frontend) { [void](Open-WorkbenchBrowser); return 0 }
            return 12
        }

        Remove-StalePidMetadata

        # Duplicate-start determinism: if a launcher-owned healthy stack already runs,
        # reuse it and succeed (no second stack is spawned).
        $ownedLive = Get-LiveOwnedPids
        if ($ownedLive.Count -gt 0 -and (Test-Health) -and (Test-BackendHealth)) {
            Write-LauncherLog 'Duplicate start detected: existing launcher-owned stack is healthy; reusing it (no second stack spawned).'
            [void](Open-WorkbenchBrowser)
            return 0
        }
        if ($ownedLive.Count -gt 0) {
            Write-LauncherLog "Launcher metadata identifies a partial/unhealthy owned stack (owned_live=$($ownedLive.Count)); recycling only verified owned processes." 'WARN'
            if (-not (Stop-OwnedStackForRecovery)) { return 15 }
        }
        Write-LauncherLog 'No launcher-owned healthy stack detected; starting a fresh stack.'

        # Fail closed BEFORE starting anything if a frontend/backend port is occupied by a
        # process that is not our own healthy stack. Never kill or replace a foreign process.
        $frontendOccupied = Test-PortOpen -PortNumber $Port
        $backendOccupied  = Test-PortOpen -PortNumber $BackendPort
        if ($frontendOccupied) {
            Write-LauncherLog "Frontend port $Port is occupied by another application. Macro Workbench was not started." 'ERROR'
            return 13
        }
        if ($backendOccupied) {
            Write-LauncherLog "Backend port $BackendPort is occupied by another application. Macro Workbench was not started." 'ERROR'
            return 14
        }

        $pythonPath = Resolve-Python
        if ([string]::IsNullOrWhiteSpace($pythonPath)) {
            Write-LauncherLog 'A Python 3 interpreter is required but was not found (no .venv and not on PATH).' 'ERROR'
            return 10
        }
        $nodePath = Resolve-Executable @('node.exe','node')
        $npmPath = Resolve-Executable @('npm.cmd','npm')
        if ([string]::IsNullOrWhiteSpace($nodePath) -or [string]::IsNullOrWhiteSpace($npmPath)) {
            Write-LauncherLog 'Node.js and npm are required but were not found on PATH. Install a supported Node.js release, then run START_MACRO_WORKBENCH.cmd again.' 'ERROR'
            return 10
        }

        try {
            $nodeVersion = (& $nodePath --version 2>&1 | Out-String).Trim()
            $npmVersion = (& $npmPath --version 2>&1 | Out-String).Trim()
            if ($LASTEXITCODE -ne 0) { throw 'npm --version failed' }
            Write-LauncherLog "Environment: python=$pythonPath node=$nodeVersion npm=$npmVersion"
        } catch {
            Write-LauncherLog "Node/npm version check failed: $($_.Exception.Message)" 'ERROR'
            return 10
        }

        if (-not (Test-Path -LiteralPath $PackageJson -PathType Leaf)) { Write-LauncherLog "Missing $PackageJson" 'ERROR'; return 11 }
        if (-not (Test-Path -LiteralPath $ServerScript -PathType Leaf)) { Write-LauncherLog "Missing $ServerScript" 'ERROR'; return 11 }

        if (Test-DependenciesNeedInstall) {
            $ciCode = Invoke-NpmCommand -NpmPath $npmPath -Arguments @('ci') -Label 'npm ci'
            if ($ciCode -ne 0) { return 20 }
        }
        if (Test-BuildNeeded) {
            $buildCode = Invoke-NpmCommand -NpmPath $npmPath -Arguments @('run','build') -Label 'frontend build'
            if ($buildCode -ne 0) { Write-LauncherLog 'Build failed; server not started.' 'ERROR'; return 21 }
        }

        # Backend must come up first so the frontend proxy has a live upstream.
        $backendPid = Start-Backend -PythonPath $pythonPath
        if ($false -eq $backendPid) { return 30 }

        $frontendPid = Start-Frontend -NodePath $nodePath
        if ($null -eq $frontendPid) {
            # Clean up our own backend if we started it.
            if ($backendPid -gt 0) { try { Stop-Process -Id $backendPid -ErrorAction Stop } catch { } }
            return 31
        }

        Write-PidMetadata -BackendPid $backendPid -FrontendPid $frontendPid
        [void](Open-WorkbenchBrowser)
        Write-LauncherLog 'Launcher completed successfully; backend + frontend continue in the background.'
        return 0
    } catch {
        Write-LauncherLog "Unhandled launcher error: $($_.Exception.Message)`n$($_.ScriptStackTrace)" 'ERROR'
        return 99
    } finally {
        if ($hasMutex) { try { $mutex.ReleaseMutex() } catch { } }
        $mutex.Dispose()
    }
}

$exitCode = Invoke-LauncherMain
exit $exitCode