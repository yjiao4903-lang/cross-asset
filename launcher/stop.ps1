[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$HostAddress = '127.0.0.1'
$Port = 8765
$HealthUrl = "http://${HostAddress}:$Port/__health"
$ExpectedApp = 'macro-workbench'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$RuntimeDir = Join-Path $PSScriptRoot '.runtime'
$LogsDir = Join-Path $PSScriptRoot 'logs'
$PidFile = Join-Path $RuntimeDir 'server.pid'
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

function Invoke-StopMain {
    Write-StopLog "Stop requested. repo=$RepoRoot"

    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
        if (Test-MacroHealth) {
            Write-StopLog 'Macro Workbench responds on port 8765, but launcher ownership metadata is missing. Refusing to kill an unverified process.' 'ERROR'
            return 41
        }
        Write-StopLog 'Macro Workbench launcher server is not running.'
        return 0
    }

    try {
        $metadata = Get-Content -LiteralPath $PidFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-StopLog 'Invalid/stale PID metadata removed; no process was killed.' 'WARN'
        return 0
    }

    $pidValue = 0
    if (-not [int]::TryParse([string]$metadata.pid, [ref]$pidValue)) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-StopLog 'Invalid/stale PID metadata removed; no process was killed.' 'WARN'
        return 0
    }

    $owned = Get-OwnedServerProcess -ProcessId $pidValue
    if ($null -eq $owned) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        if (Test-MacroHealth) {
            Write-StopLog "PID $pidValue is not the launcher-owned server, while a Macro Workbench health endpoint still responds. Refusing to kill any process." 'ERROR'
            return 42
        }
        Write-StopLog "Stale PID $pidValue removed; launcher-owned server was not running." 'WARN'
        return 0
    }

    try {
        Stop-Process -Id $pidValue -ErrorAction Stop
        try { Wait-Process -Id $pidValue -Timeout 5 -ErrorAction SilentlyContinue } catch { }
        Write-StopLog "Stopped launcher-owned server PID $pidValue."
    } catch {
        Write-StopLog "Failed to stop launcher-owned server PID $pidValue: $($_.Exception.Message)" 'ERROR'
        return 43
    } finally {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }

    for ($i = 0; $i -lt 10; $i++) {
        if (-not (Test-MacroHealth)) {
            Write-StopLog 'Health endpoint is no longer responding; stop PASS.'
            return 0
        }
        Start-Sleep -Milliseconds 250
    }

    Write-StopLog 'The owned process was stopped, but the Macro Workbench health endpoint still responds. Another instance may exist; no additional process was killed.' 'ERROR'
    return 44
}

$exitCode = Invoke-StopMain
exit $exitCode
