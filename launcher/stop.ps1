[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$HostAddress = '127.0.0.1'
$Port = 8765
$BackendPort = 8008
$HealthUrl = "http://${HostAddress}:$Port/__health"
$BackendHealthUrl = "http://${HostAddress}:${BackendPort}/api/health"
$ExpectedApp = 'macro-workbench'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$RuntimeDir = Join-Path $PSScriptRoot '.runtime'
$LogsDir = Join-Path $PSScriptRoot 'logs'
$PidFile = Join-Path $RuntimeDir 'servers.pid'
$LauncherLog = Join-Path $LogsDir 'launcher.log'
$ServerScript = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'server.mjs'))

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogsDir | Out-Null

function Write-StopLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO','WARN','ERROR')][string]$Level = 'INFO'
    )
    $timestamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffK')
    $line = "$timestamp [$Level] STOP $Message"
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding UTF8
    if ($Level -eq 'ERROR') { Write-Host $Message -ForegroundColor Red }
    elseif ($Level -eq 'WARN') { Write-Host $Message -ForegroundColor Yellow }
    else { Write-Host $Message }
}

function Test-Url {
    param([string]$Uri, [int]$TimeoutSec = 1)
    try {
        return [int](Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSec).StatusCode
    } catch {
        if ($_.Exception.Response) {
            try { return [int]$_.Exception.Response.StatusCode } catch { return $null }
        }
        return $null
    }
}

function Test-Health { return ((Test-Url -Uri $HealthUrl) -eq 200) }

function Test-OwnedProcess {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($null -eq $process) { return $false }
        $commandLine = [string]$process.CommandLine
        if ([string]::IsNullOrWhiteSpace($commandLine)) { return $false }
        if ($commandLine.IndexOf($ServerScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
        if ($commandLine.IndexOf('decision_support.snapshot_cli', [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
        return $false
    } catch { return $false }
}

function Invoke-StopMain {
    Write-StopLog "Stop requested. repo=$RepoRoot"

    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
        if (Test-Health -or ((Test-Url -Uri $BackendHealthUrl) -eq 200)) {
            Write-StopLog 'Workbench/backend responds but launcher ownership metadata is missing. Refusing to kill unverified processes.' 'ERROR'
            return 41
        }
        Write-StopLog 'Macro Workbench launcher processes are not running.'
        return 0
    }

    $meta = $null
    try { $meta = Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
    if ($null -eq $meta) {
        if (Test-Health -or ((Test-Url -Uri $BackendHealthUrl) -eq 200)) {
            Write-StopLog 'PID metadata is corrupted while a Workbench health endpoint still responds. Refusing to delete ownership evidence or kill any process.' 'ERROR'
            return 43
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-StopLog 'Invalid/stale PID metadata removed only after health endpoints were confirmed down; no process was killed.' 'WARN'
        return 0
    }

    $targetPids = New-Object System.Collections.Generic.List[int]
    foreach ($entry in @($meta.backend, $meta.frontend)) {
        if ($null -eq $entry) { continue }
        $pidValue = 0
        if ([int]::TryParse([string]$entry.pid, [ref]$pidValue)) {
            if (Test-OwnedProcess -ProcessId $pidValue) { $targetPids.Add($pidValue) }
            else { Write-StopLog "PID $pidValue is not a launcher-owned process; skipping." 'WARN' }
        }
    }

    if ($targetPids.Count -eq 0) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        if (Test-Health -or ((Test-Url -Uri $BackendHealthUrl) -eq 200)) {
            Write-StopLog 'No launcher-owned PID found while health endpoint still responds. Refusing to kill any foreign process.' 'ERROR'
            return 42
        }
        Write-StopLog 'Stale PID metadata removed; nothing launcher-owned to stop.' 'WARN'
        return 0
    }

    foreach ($procId in $targetPids) {
        if (Test-OwnedProcess -ProcessId $procId) {
            try {
                Stop-Process -Id $procId -ErrorAction Stop
                try { Wait-Process -Id $procId -Timeout 5 -ErrorAction SilentlyContinue } catch { }
                Write-StopLog "Stopped launcher-owned process PID $procId."
            } catch {
                Write-StopLog "Failed to stop launcher-owned PID $($procId): $($_.Exception.Message)" 'ERROR'
            }
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue

    for ($i = 0; $i -lt 10; $i++) {
        if (-not (Test-Url -Uri $HealthUrl) -and (-not (Test-Url -Uri $BackendHealthUrl))) {
            Write-StopLog 'Health endpoints no longer respond; stop PASS.'
            return 0
        }
        Start-Sleep -Milliseconds 250
    }

    Write-StopLog 'Owned processes were stopped, but health endpoints still respond. Another instance may exist; no additional process was killed.' 'ERROR'
    return 44
}

$exitCode = Invoke-StopMain
exit $exitCode