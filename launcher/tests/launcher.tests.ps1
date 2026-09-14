[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$OriginalRepo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$PowerShellExe = (Get-Process -Id $PID).Path
$OriginalPath = $env:PATH
$OriginalNoBrowser = $env:MACRO_WORKBENCH_NO_BROWSER
$env:MACRO_WORKBENCH_NO_BROWSER = '1'
$TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("macro-workbench-launcher-test-" + [guid]::NewGuid().ToString('N'))
$Repo = Join-Path $TestRoot 'repo'
$Launcher = Join-Path $Repo 'launcher\launcher.ps1'
$Stopper = Join-Path $Repo 'launcher\stop.ps1'
$PidFile = Join-Path $Repo 'launcher\.runtime\server.pid'
$LauncherLog = Join-Path $Repo 'launcher\logs\launcher.log'
$HealthUrl = 'http://127.0.0.1:8765/__health'
$ForeignScript = Join-Path $TestRoot 'foreign.mjs'
$UnrelatedProcess = $null
$ForeignProcess = $null
$Passed = 0
$Failed = 0

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERT FAILED: $Message" }
}

function Invoke-ChildPowerShell {
    param(
        [Parameter(Mandatory = $true)][string]$Script,
        [hashtable]$Environment = @{}
    )

    $saved = @{}
    foreach ($name in $Environment.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, [string]$Environment[$name], 'Process')
    }
    try {
        $process = Start-Process -FilePath $PowerShellExe `
            -ArgumentList "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$Script`"" `
            -WorkingDirectory $Repo `
            -Wait -PassThru -NoNewWindow
        return $process.ExitCode
    } finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
        }
    }
}

function Get-HealthPayload {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 1
        if ($response.StatusCode -ne 200) { return $null }
        return ($response.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Wait-HealthDown {
    for ($i = 0; $i -lt 20; $i++) {
        if ($null -eq (Get-HealthPayload)) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Get-RecordedPid {
    Assert-True (Test-Path -LiteralPath $PidFile) 'PID metadata should exist'
    return [int]((Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json).pid)
}

function Run-Test {
    param([string]$Name, [scriptblock]$Body)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    try {
        & $Body
        $script:Passed++
        Write-Host "PASS: $Name" -ForegroundColor Green
    } catch {
        $script:Failed++
        Write-Host "FAIL: $Name`n$($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

function Copy-TestRepo {
    New-Item -ItemType Directory -Force -Path $Repo, (Join-Path $Repo 'frontend'), (Join-Path $Repo 'launcher') | Out-Null
    Copy-Item -LiteralPath (Join-Path $OriginalRepo 'launcher\launcher.ps1') -Destination (Join-Path $Repo 'launcher\launcher.ps1')
    Copy-Item -LiteralPath (Join-Path $OriginalRepo 'launcher\stop.ps1') -Destination (Join-Path $Repo 'launcher\stop.ps1')
    Copy-Item -LiteralPath (Join-Path $OriginalRepo 'launcher\server.mjs') -Destination (Join-Path $Repo 'launcher\server.mjs')

    foreach ($file in @('package.json','package-lock.json','index.html','vite.config.js')) {
        Copy-Item -LiteralPath (Join-Path $OriginalRepo "frontend\$file") -Destination (Join-Path $Repo "frontend\$file")
    }
    Copy-Item -LiteralPath (Join-Path $OriginalRepo 'frontend\src') -Destination (Join-Path $Repo 'frontend\src') -Recurse
}

try {
    if ($null -ne (Get-HealthPayload)) {
        throw 'Port 8765 is already serving an HTTP health endpoint before launcher tests; aborting to avoid touching an existing process.'
    }

    Copy-TestRepo

    Run-Test 'T1 fresh machine-like state: npm ci + build + health' {
        Assert-True (-not (Test-Path (Join-Path $Repo 'frontend\node_modules'))) 'node_modules should start absent'
        Assert-True (-not (Test-Path (Join-Path $Repo 'frontend\dist'))) 'dist should start absent'
        $code = Invoke-ChildPowerShell -Script $Launcher
        Assert-True ($code -eq 0) "launcher exit expected 0, got $code"
        $health = Get-HealthPayload
        Assert-True ($health.app -eq 'macro-workbench' -and $health.status -eq 'ok') 'health payload should identify Macro Workbench'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'npm ci completed successfully') 'npm ci should run in fresh state'
        Assert-True ($log -match 'frontend build completed successfully') 'build should run in fresh state'
    }

    Run-Test 'T2 existing fresh build skips npm ci and build' {
        $stopCode = Invoke-ChildPowerShell -Script $Stopper
        Assert-True ($stopCode -eq 0) 'precondition stop should succeed'
        Assert-True (Wait-HealthDown) 'health should be down before T2'
        Clear-Content -LiteralPath $LauncherLog
        $code = Invoke-ChildPowerShell -Script $Launcher
        Assert-True ($code -eq 0) 'launcher should succeed with existing build'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'npm ci skipped') 'npm ci should be skipped'
        Assert-True ($log -match 'build skipped') 'build should be skipped'
    }

    Run-Test 'T3 source newer than dist triggers build' {
        Assert-True ((Invoke-ChildPowerShell -Script $Stopper) -eq 0) 'stop should succeed before T3'
        Assert-True (Wait-HealthDown) 'health should be down before T3'
        $source = Join-Path $Repo 'frontend\src\main.jsx'
        (Get-Item -LiteralPath $source).LastWriteTimeUtc = (Get-Date).ToUniversalTime().AddSeconds(5)
        Clear-Content -LiteralPath $LauncherLog
        Assert-True ((Invoke-ChildPowerShell -Script $Launcher) -eq 0) 'launcher should rebuild after source touch'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'newer than dist/index.html -> build required') 'freshness decision should require build'
        Assert-True ($log -match 'frontend build completed successfully') 'build should complete'
    }

    Run-Test 'T4 duplicate start reuses the same server PID' {
        $pidBefore = Get-RecordedPid
        Clear-Content -LiteralPath $LauncherLog
        Assert-True ((Invoke-ChildPowerShell -Script $Launcher) -eq 0) 'duplicate launcher should succeed'
        $pidAfter = Get-RecordedPid
        Assert-True ($pidBefore -eq $pidAfter) 'duplicate launch must not create a second server PID'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'Duplicate start detected') 'duplicate launch should be explicitly detected'
    }

    Run-Test 'T5 stop only terminates launcher-owned server' {
        $UnrelatedProcess = Start-Process -FilePath 'node.exe' -ArgumentList @('-e','setInterval(()=>{},1000)') -PassThru -WindowStyle Hidden
        $macroPid = Get-RecordedPid
        Assert-True ((Invoke-ChildPowerShell -Script $Stopper) -eq 0) 'STOP should succeed'
        Assert-True (Wait-HealthDown) 'health should be down after STOP'
        Assert-True ($null -eq (Get-Process -Id $macroPid -ErrorAction SilentlyContinue)) 'Macro server PID should be gone'
        Assert-True ($null -ne (Get-Process -Id $UnrelatedProcess.Id -ErrorAction SilentlyContinue)) 'unrelated node process must remain alive'
    }

    Run-Test 'T6 stale PID metadata is cleaned automatically' {
        New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null
        @{ pid = 999999; server_script = 'stale'; repo_root = $Repo } | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
        Clear-Content -LiteralPath $LauncherLog
        Assert-True ((Invoke-ChildPowerShell -Script $Launcher) -eq 0) 'launcher should recover from stale PID'
        $newPid = Get-RecordedPid
        Assert-True ($newPid -ne 999999) 'stale PID should be replaced by current server PID'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'Removing stale PID metadata') 'stale PID cleanup should be logged'
        Assert-True ((Invoke-ChildPowerShell -Script $Stopper) -eq 0) 'stop should succeed after stale PID recovery'
        Assert-True (Wait-HealthDown) 'health should be down before foreign-port test'
    }

    Run-Test 'T7 foreign port occupancy is preserved and launcher fails closed' {
        @'
import http from 'node:http'
const server = http.createServer((req, res) => {
  res.writeHead(200, {'content-type':'application/json'})
  res.end(JSON.stringify({status:'ok',app:'not-macro-workbench'}))
})
server.listen(8765, '127.0.0.1')
setInterval(() => {}, 1000)
'@ | Set-Content -LiteralPath $ForeignScript -Encoding UTF8
        $ForeignProcess = Start-Process -FilePath 'node.exe' -ArgumentList @("`"$ForeignScript`"") -PassThru -WindowStyle Hidden
        Start-Sleep -Milliseconds 750
        Clear-Content -LiteralPath $LauncherLog
        $code = Invoke-ChildPowerShell -Script $Launcher
        Assert-True ($code -ne 0) 'launcher must fail when a foreign process owns port 8765'
        Assert-True ($null -ne (Get-Process -Id $ForeignProcess.Id -ErrorAction SilentlyContinue)) 'foreign process must remain alive'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'Port 8765 is already in use by another application') 'foreign-port message should be explicit'
        Stop-Process -Id $ForeignProcess.Id -Force -ErrorAction SilentlyContinue
        $ForeignProcess = $null
        Assert-True (Wait-HealthDown) 'foreign health endpoint should be down after test cleanup'
    }

    Run-Test 'T8 missing Node/npm reports a clear nonzero failure without install attempt' {
        Clear-Content -LiteralPath $LauncherLog
        $minimalPath = "$env:SystemRoot\System32;$env:SystemRoot"
        $code = Invoke-ChildPowerShell -Script $Launcher -Environment @{ PATH = $minimalPath }
        Assert-True ($code -ne 0) 'launcher must fail when node/npm are unavailable'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'Node.js and npm are required but were not found on PATH') 'missing Node message should be clear'
        Assert-True ($log -match 'will not download or modify Node.js automatically') 'launcher must explicitly avoid auto-install behavior'
    }

    Run-Test 'T9 build failure blocks server/browser and returns nonzero' {
        $packagePath = Join-Path $Repo 'frontend\package.json'
        $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
        $package.scripts.build = 'node fail-build.mjs'
        $package | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $packagePath -Encoding UTF8
        "process.exit(7)" | Set-Content -LiteralPath (Join-Path $Repo 'frontend\fail-build.mjs') -Encoding UTF8
        $source = Join-Path $Repo 'frontend\src\main.jsx'
        (Get-Item -LiteralPath $source).LastWriteTimeUtc = (Get-Date).ToUniversalTime().AddSeconds(10)
        Clear-Content -LiteralPath $LauncherLog
        $code = Invoke-ChildPowerShell -Script $Launcher
        Assert-True ($code -ne 0) 'launcher must return nonzero on build failure'
        Assert-True ($null -eq (Get-HealthPayload)) 'server must not start after build failure'
        $log = Get-Content -LiteralPath $LauncherLog -Raw
        Assert-True ($log -match 'Build failed; the static server and browser will not be started') 'build-failure containment should be logged'
    }

    Write-Host "`nLauncher integration tests: $Passed passed, $Failed failed" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "`nLauncher integration tests aborted: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    $env:PATH = $OriginalPath
    if ($null -eq $OriginalNoBrowser) { Remove-Item Env:MACRO_WORKBENCH_NO_BROWSER -ErrorAction SilentlyContinue }
    else { $env:MACRO_WORKBENCH_NO_BROWSER = $OriginalNoBrowser }

    if (Test-Path -LiteralPath $Stopper) {
        try { & $PowerShellExe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $Stopper | Out-Null } catch { }
    }
    foreach ($proc in @($UnrelatedProcess, $ForeignProcess)) {
        if ($null -ne $proc) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $TestRoot) {
        Remove-Item -LiteralPath $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
