[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$HostAddress = '127.0.0.1'
$Port = 8765
$AppUrl = "http://${HostAddress}:$Port"
$HealthUrl = "$AppUrl/__health"
$ExpectedApp = 'macro-workbench'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$FrontendDir = Join-Path $RepoRoot 'frontend'
$PackageJson = Join-Path $FrontendDir 'package.json'
$PackageLock = Join-Path $FrontendDir 'package-lock.json'
$DistIndex = Join-Path $FrontendDir 'dist\index.html'
$RuntimeDir = Join-Path $PSScriptRoot '.runtime'
$LogsDir = Join-Path $PSScriptRoot 'logs'
$PidFile = Join-Path $RuntimeDir 'server.pid'
$LauncherLog = Join-Path $LogsDir 'launcher.log'
$ServerStdoutLog = Join-Path $LogsDir 'server-stdout.log'
$ServerStderrLog = Join-Path $LogsDir 'server-stderr.log'
$ServerScript = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'server.mjs'))
$MutexName = 'Local\MacroWorkbenchLauncher8765'

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogsDir | Out-Null

function Write-LauncherLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO','WARN','ERROR')][string]$Level = 'INFO'
    )
    $timestamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffK')
    $line = "$timestamp [$Level] $Message"
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding UTF8
    if ($Level -eq 'ERROR') {
        Write-Host $Message -ForegroundColor Red
    } elseif ($Level -eq 'WARN') {
        Write-Host $Message -ForegroundColor Yellow
    } else {
        Write-Host $Message
    }
}

function Test-TruthyEnv {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $false }
    return @('1','true','yes','on') -contains $value.Trim().ToLowerInvariant()
}

function Test-MacroHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 1
        if ([int]$response.StatusCode -ne 200) { return $false }
        $payload = $response.Content | ConvertFrom-Json
        return ($payload.status -eq 'ok' -and $payload.app -eq $ExpectedApp)
    } catch {
        return $false
    }
}

function Test-PortOpen {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect($HostAddress, $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(350)) { return $false }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-PidMetadata {
    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) { return $null }
    try {
        return (Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8 | ConvertFrom-Json)
    } catch {
        Write-LauncherLog "Invalid PID metadata found; removing stale file: $PidFile" 'WARN'
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }
}

function Get-OwnedServerProcess {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($null -eq $process) { return $null }
        $commandLine = [string]$process.CommandLine
        if ([string]::IsNullOrWhiteSpace($commandLine)) { return $null }
        if ($commandLine.IndexOf($ServerScript, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { return $null }
        return $process
    } catch {
        return $null
    }
}

function Remove-StalePidMetadata {
    $metadata = Get-PidMetadata
    if ($null -eq $metadata) { return }

    $pidValue = 0
    if (-not [int]::TryParse([string]$metadata.pid, [ref]$pidValue)) {
        Write-LauncherLog 'PID metadata did not contain a valid process id; removing it.' 'WARN'
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $owned = Get-OwnedServerProcess -ProcessId $pidValue
    if ($null -eq $owned) {
        Write-LauncherLog "Removing stale PID metadata for non-owned/dead PID $pidValue." 'WARN'
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
        Write-LauncherLog "Macro Workbench is healthy, but the browser could not be opened automatically. Open $AppUrl manually. Error: $($_.Exception.Message)" 'WARN'
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
        $process = Start-Process -FilePath $NpmPath `
            -ArgumentList $Arguments `
            -WorkingDirectory $FrontendDir `
            -NoNewWindow `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -Wait `
            -PassThru

        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                Get-Content -LiteralPath $path -Encoding UTF8 | ForEach-Object {
                    $text = [string]$_
                    Add-Content -LiteralPath $LauncherLog -Value $text -Encoding UTF8
                    Write-Host $text
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
    if (-not (Test-Path -LiteralPath $nodeModules -PathType Container)) {
        Write-LauncherLog 'Dependency decision: node_modules missing -> npm ci required.'
        return $true
    }

    if (Test-Path -LiteralPath $PackageLock -PathType Leaf) {
        $installStamp = Join-Path $nodeModules '.package-lock.json'
        if (-not (Test-Path -LiteralPath $installStamp -PathType Leaf)) {
            Write-LauncherLog 'Dependency decision: node_modules install stamp missing -> npm ci required.'
            return $true
        }
        $lockTime = (Get-Item -LiteralPath $PackageLock).LastWriteTimeUtc
        $stampTime = (Get-Item -LiteralPath $installStamp).LastWriteTimeUtc
        if ($lockTime -gt $stampTime) {
            Write-LauncherLog 'Dependency decision: package-lock.json newer than node_modules install stamp -> npm ci required.'
            return $true
        }
    }

    Write-LauncherLog 'Dependency decision: existing node_modules is reusable; npm ci skipped.'
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
    if (-not (Test-Path -LiteralPath $DistIndex -PathType Leaf)) {
        Write-LauncherLog 'Build decision: frontend/dist/index.html missing -> build required.'
        return $true
    }

    $distTime = (Get-Item -LiteralPath $DistIndex).LastWriteTimeUtc
    foreach ($input in (Get-BuildInputs)) {
        if ($input.LastWriteTimeUtc -gt $distTime) {
            Write-LauncherLog "Build decision: $($input.FullName) is newer than dist/index.html -> build required."
            return $true
        }
    }

    Write-LauncherLog 'Build decision: frontend/dist is fresh; build skipped.'
    return $false
}

function Start-FrontendServer {
    param([Parameter(Mandatory = $true)][string]$NodePath)

    if (Test-Path -LiteralPath $ServerStdoutLog) { Remove-Item -LiteralPath $ServerStdoutLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $ServerStderrLog) { Remove-Item -LiteralPath $ServerStderrLog -Force -ErrorAction SilentlyContinue }

    $process = Start-Process -FilePath $NodePath `
        -ArgumentList @("`"$ServerScript`"") `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $ServerStdoutLog `
        -RedirectStandardError $ServerStderrLog `
        -PassThru

    $metadata = [ordered]@{
        pid = $process.Id
        host = $HostAddress
        port = $Port
        server_script = $ServerScript
        repo_root = $RepoRoot
        started_at = (Get-Date).ToString('o')
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
    Write-LauncherLog "Server process started with PID $($process.Id)."
    return $process
}

function Stop-StartedProcessSafely {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    $owned = Get-OwnedServerProcess -ProcessId $ProcessId
    if ($null -eq $owned) {
        Write-LauncherLog "Cleanup skipped: PID $ProcessId is no longer the launcher-owned server." 'WARN'
        return
    }
    try {
        Stop-Process -Id $ProcessId -ErrorAction Stop
        Write-LauncherLog "Cleaned up launcher-started server PID $ProcessId."
    } catch {
        Write-LauncherLog "Failed to clean up launcher-started PID $($ProcessId): $($_.Exception.Message)" 'WARN'
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Wait-ForMacroHealth {
    param([int]$Attempts = 30, [int]$DelayMs = 500)
    for ($i = 1; $i -le $Attempts; $i++) {
        if (Test-MacroHealth) {
            Write-LauncherLog "Health PASS on attempt $i/$Attempts."
            return $true
        }
        Start-Sleep -Milliseconds $DelayMs
    }
    return $false
}

function Invoke-LauncherMain {
    Write-LauncherLog "Launcher start. repo=$RepoRoot port=${HostAddress}:$Port"

    $mutex = New-Object System.Threading.Mutex($false, $MutexName)
    $hasMutex = $false
    try {
        try {
            $hasMutex = $mutex.WaitOne(0)
        } catch [System.Threading.AbandonedMutexException] {
            $hasMutex = $true
            Write-LauncherLog 'Recovered abandoned launcher mutex.' 'WARN'
        }

        if (-not $hasMutex) {
            Write-LauncherLog 'Another launcher process is active; waiting for the existing launch to become healthy.' 'WARN'
            if (Wait-ForMacroHealth -Attempts 60 -DelayMs 500) {
                [void](Open-WorkbenchBrowser)
                return 0
            }
            Write-LauncherLog 'Another launcher is still preparing Macro Workbench and no healthy server is available yet. No second server was started.' 'ERROR'
            return 12
        }

        Remove-StalePidMetadata

        if (Test-MacroHealth) {
            Write-LauncherLog 'Duplicate start detected: existing Macro Workbench server is healthy; reusing it.'
            [void](Open-WorkbenchBrowser)
            return 0
        }

        if (Test-PortOpen) {
            Write-LauncherLog 'Port 8765 is already in use by another application. Macro Workbench was not started.' 'ERROR'
            return 13
        }

        $nodePath = Resolve-Executable @('node.exe','node')
        $npmPath = Resolve-Executable @('npm.cmd','npm')
        if ([string]::IsNullOrWhiteSpace($nodePath) -or [string]::IsNullOrWhiteSpace($npmPath)) {
            Write-LauncherLog 'Node.js and npm are required but were not found on PATH. Install a supported Node.js release, then run START_MACRO_WORKBENCH.cmd again. The launcher will not download or modify Node.js automatically.' 'ERROR'
            return 10
        }

        try {
            $nodeVersion = (& $nodePath --version 2>&1 | Out-String).Trim()
            $npmVersion = (& $npmPath --version 2>&1 | Out-String).Trim()
            if ($LASTEXITCODE -ne 0) { throw 'npm --version failed' }
            Write-LauncherLog "Environment: node=$nodeVersion npm=$npmVersion"
        } catch {
            Write-LauncherLog "Node/npm version check failed: $($_.Exception.Message)" 'ERROR'
            return 10
        }

        if (-not (Test-Path -LiteralPath $PackageJson -PathType Leaf)) {
            Write-LauncherLog "Repository structure error: missing $PackageJson" 'ERROR'
            return 11
        }
        if (-not (Test-Path -LiteralPath $ServerScript -PathType Leaf)) {
            Write-LauncherLog "Repository structure error: missing $ServerScript" 'ERROR'
            return 11
        }

        if (Test-DependenciesNeedInstall) {
            $ciCode = Invoke-NpmCommand -NpmPath $npmPath -Arguments @('ci') -Label 'npm ci'
            if ($ciCode -ne 0) { return 20 }
        }

        if (Test-BuildNeeded) {
            $buildCode = Invoke-NpmCommand -NpmPath $npmPath -Arguments @('run','build') -Label 'frontend build'
            if ($buildCode -ne 0) {
                Write-LauncherLog 'Build failed; the static server and browser will not be started.' 'ERROR'
                return 21
            }
        }

        # Future backend lifecycle belongs before this point:
        # start backend -> backend health -> start frontend -> frontend health -> browser.
        # V1 intentionally launches the frontend only.
        $serverProcess = Start-FrontendServer -NodePath $nodePath
        if (-not (Wait-ForMacroHealth -Attempts 30 -DelayMs 500)) {
            Write-LauncherLog 'Server failed to become healthy within the launch window.' 'ERROR'
            Stop-StartedProcessSafely -ProcessId $serverProcess.Id
            return 30
        }

        [void](Open-WorkbenchBrowser)
        Write-LauncherLog 'Launcher completed successfully; server continues in the background.'
        return 0
    } catch {
        Write-LauncherLog "Unhandled launcher error: $($_.Exception.Message)`n$($_.ScriptStackTrace)" 'ERROR'
        return 99
    } finally {
        if ($hasMutex) {
            try { $mutex.ReleaseMutex() } catch { }
        }
        $mutex.Dispose()
    }
}

$exitCode = Invoke-LauncherMain
exit $exitCode
