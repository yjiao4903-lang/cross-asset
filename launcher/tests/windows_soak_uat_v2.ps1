[CmdletBinding()]
param(
    [string]$Python = $env:CROSS_ASSET_PYTHON,
    [string]$ArtifactRoot = 'artifacts/windows_uat_v2',
    [int]$ConnectivityAttempts = 3,
    [int]$ConnectivityRetrySeconds = 60
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $Here '..\..'))
$Launcher = Join-Path $Here '..\launcher.ps1'
$Stopper = Join-Path $Here '..\stop.ps1'
$ProviderProbe = Join-Path $Here 'provider_connectivity_v2.py'
$RealSnapshotDriver = Join-Path $Here 'real_snapshot_uat_v2.py'
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

$NodeCmd = Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1
$NpmCmd = Get-Command npm -ErrorAction SilentlyContinue | Select-Object -First 1

$Soak = New-Object System.Collections.Generic.List[object]
$Ownership = New-Object System.Collections.Generic.List[object]
$Blockers = New-Object System.Collections.Generic.List[object]
$Sentinels = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ForeignProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-JsonFile([string]$Path, [object]$Payload) {
    $Payload | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Safe-Version([string]$Command, [string[]]$Arguments = @()) {
    try { return ((& $Command @Arguments 2>&1 | Out-String).Trim()) } catch { return $null }
}

function Port-Owners([int]$Port) {
    $rows = @()
    try {
        foreach ($conn in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)) {
            $pidValue = [int]$conn.OwningProcess
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
            $rows += [pscustomobject]@{
                port = $Port
                pid = $pidValue
                name = if ($process) { [string]$process.Name } else { $null }
                command_line = if ($process) { ([string]$process.CommandLine).Substring(0, [Math]::Min(240, ([string]$process.CommandLine).Length)) } else { $null }
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
    $health = Json-Url "$AppUrl/api/health"
    $latest = Json-Url "$AppUrl/api/snapshot/latest"
    $history = Json-Url "$AppUrl/api/snapshots"
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

function Invoke-LauncherCode([switch]$AllowBrowser) {
    if ($AllowBrowser) { Remove-Item Env:MACRO_WORKBENCH_NO_BROWSER -ErrorAction SilentlyContinue }
    else { $env:MACRO_WORKBENCH_NO_BROWSER = '1' }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher | Out-Host
    return $LASTEXITCODE
}

function Invoke-StopCode {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Stopper | Out-Host
    return $LASTEXITCODE
}

function Wait-PortDown([int]$Port, [int]$Seconds = 8) {
    for ($i = 0; $i -lt ($Seconds * 4); $i++) {
        if (@(Port-Owners $Port).Count -eq 0) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Start-Sentinel([string]$Kind) {
    if ($Kind -eq 'python') {
        $p = Start-Process -FilePath $Python -ArgumentList @('-c', 'import time; time.sleep(900)') -WindowStyle Hidden -PassThru
    } else {
        if (-not $NodeCmd) { return $null }
        $p = Start-Process -FilePath $NodeCmd.Source -ArgumentList @('-e', 'setTimeout(()=>{},900000)') -WindowStyle Hidden -PassThru
    }
    $Sentinels.Add($p)
    return $p
}

function Sentinel-Alive([System.Diagnostics.Process]$Process) {
    if ($null -eq $Process) { return $true }
    return [bool](Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)
}

function Start-ForeignPort([int]$Port) {
    $p = Start-Process -FilePath $Python -ArgumentList @('-m', 'http.server', "$Port", '--bind', '127.0.0.1') -WorkingDirectory $ArtifactRootPath -WindowStyle Hidden -PassThru
    $ForeignProcesses.Add($p)
    Start-Sleep -Milliseconds 1200
    return $p
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
            "--user-data-dir=$profile", '--virtual-time-budget=6000', '--dump-dom', $AppUrl
        )
        $dom = (& $browser @argsBrowser 2>&1 | Out-String)
        $hasRun = (-not [string]::IsNullOrWhiteSpace($ExpectedRunId)) -and ($dom.IndexOf($ExpectedRunId, [StringComparison]::OrdinalIgnoreCase) -ge 0)
        $noDemo = $dom.IndexOf('DEMO / GOLDEN', [StringComparison]::OrdinalIgnoreCase) -lt 0
        $available = $dom.IndexOf('snapshot-unavailable', [StringComparison]::OrdinalIgnoreCase) -lt 0
        $pass = $hasRun -and $noDemo -and $available
        $path = Join-Path $ArtifactRootPath 'BROWSER_DOM.html'
        Set-Content -LiteralPath $path -Value $dom -Encoding UTF8
        return [pscustomobject]@È][\YH	YNÈ\ÜÈH	\ÜÎÈœ›ÝÜÙ\ˆH	œ›ÝÜÙ\ŽÈ]Z[Hœ[—ÚYI\Ô[ˆ›×Ù[[ÏI›Ñ[[ÈÛ˜\ÚÝØ]˜Z[X›OI]˜Z[X›HÛOI]ˆBˆHØ]ÚÂˆ™]\›ˆÜØÝ\ÝÛ[Øš™XÝP²GFV×FVBÒGG'VS²72ÒFfÇ6S²'&÷w6W"ÒF'&÷w6W#²FWF–ÂÒEòäW†6WF–öâäÖW76vRÐ¢Ð§Ð ¦gVæ7F–öâw&—FRÔÖ&¶F÷väÖG&—‚…·7G&–æuÒEF‚Â·7G&–æuÒEF—FÆRÂ¶ö&¦V7EµÕÒE&÷w2’°¢FÆ–æW2ÒæWrÔö&¦V7B7—7FVÒä6öÆÆV7F–öç2ävVæW&–2äÆ—7E·7G&–æuÐ¢FÆ–æW2äFB‚"2EF—FÆR"¢FÆ–æW2äFB‚rr¢FÆ–æW2äFB‚wÂ66Væ&–òÂ6FVv÷'’Â&W7VÇBÂFWF–ÂÂr¢FÆ–æW2äFB‚wÂÒÒ×ÂÒÒ×ÂÒÒ×ÂÒÒ×Âr¢f÷&V6‚‚G&÷r–âE&÷w2’°¢FFWF–ÂÒ…·7G&–æuÒG&÷ræFWF–Â’å&WÆ6R‚wÂrÂuÇÂr’å&WÆ6R‚&""Ârr’å&WÆ6R‚&â"Ârr¢FÆ–æW2äFB‚'ÂB‚G&÷rç66Væ&–ò’ÂB‚G&÷ræ6FVv÷'’’ÂB†–b‚G&÷rç72’²u52wÒVÇ6R²td”ÂwÒ’ÂFFWF–ÂÂ"¢Ð¢FÆ–æW2äFB‚rr¢6WBÔ6öçFVçBÔÆ—FW&ÅF‚EF‚ÕfÇVRFÆ–æW2ÔVæ6öF–ærUDc€§Ð ¢2†6R¢æF—fRVçf—&öæÖVçB6Vç7W2à¢F÷2ÒvWBÔ6–Ô–ç7Fæ6Rv–ã3%ô÷W&F–æu7—7FVÒÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVP¢FVçf—&öæÖVçBÒ¶÷&FW&VEÔ°¢6öçG&7BÒut”äDõu2Õ$TÂÕ4ä4„õBÕ4ô²ÕTBÕc"p¢vVæW&FVEöBÒ„vWBÔFFR’åFõ7G&–ær‚vòr¢v–æF÷w2Ò–b‚F÷2’²²6F–öâÒF÷2ä6F–öã²fW'6–öâÒF÷2åfW'6–öã²'V–ÆBÒF÷2ä'V–ÆDçVÖ&W"ÒÒVÇ6R²FçVÆÂÐ¢÷vW'6†VÆÂÒE5fW'6–öåF&ÆRå5fW'6–öâåFõ7G&–ær‚¢—F†öâÒ²F‚ÒE—F†öã²fW'6–öâÒ…6fRÕfW'6–öâE—F†öâ‚rÒ×fW'6–öâr’’Ð¢æöFRÒ²F‚Ò–b‚DæöFT6ÖB’²DæöFT6ÖBå6÷W&6WÒVÇ6R²FçVÆÇÓ²fW'6–öâÒ–b‚DæöFT6ÖB’²…6fRÕfW'6–öâDæöFT6ÖBå6÷W&6R‚rÒ×fW'6–öâr’—ÒVÇ6R²FçVÆÇÒÐ¢çÒÒ²F‚Ò–b‚DçÔ6ÖB’²DçÔ6ÖBå6÷W&6WÒVÇ6R²FçVÆÇÓ²fW'6–öâÒ–b‚DçÔ6ÖB’²…6fRÕfW'6–öâDçÔ6ÖBå6÷W&6R‚rÒ×fW'6–öâr’—ÒVÇ6R²FçVÆÇÒÐ¢&Wõ÷&ö÷BÒE&Wõ&ö÷@¢fVçeöW†—7G2ÒFW7BÕF‚ÔÆ—FW&ÅF‚„¦ö–âÕF‚E&Wõ&ö÷BrçfVçbr’ÕF…G—R6öçF–æW ¢æöFUöÖöGVÆW5öW†—7G2ÒFW7BÕF‚ÔÆ—FW&ÅF‚„¦ö–âÕF‚E&Wõ&ö÷Bvg&öçFVæEÆæöFUöÖöGVÆW2r’ÕF…G—R6öçF–æW ¢F—7EöW†—7G2ÒFW7BÕF‚ÔÆ—FW&ÅF‚„¦ö–âÕF‚E&Wõ&ö÷Bvg&öçFVæEÆF—7EÆ–æFW‚æ‡FÖÂr’ÕF…G—RÆV`¢&÷‡•öVçf—&öæÖVçBÒ°¢…EEõ$õ…’Ò–b‚FVçc¤…EEõ$õ‚’²v6öæf–wW&VBwÒVÇ6R²FçVÆÇÐ¢…EE5õ$õ…’Ò–b‚FVçc¤…EE5õ$õ…’’²v6öæf–wW&VBwÒVÇ6R²FçVÆÇÐ¢äõõ$õ…’Ò–b‚FVçc¤äõõ$õ…’’²FVçc¤äõõ$õ…’å7V'7G&–ærƒÂ´ÖF…Ó£¤Ö–âƒ#ÂFVçc¤äõõ$õ…’äÆVæwF‚’—ÒVÇ6R²FçVÆÇÐ¢Ð¢÷'G2Ò°¢ƒ‚Ò…÷'BÔ÷væW'2ƒ‚¢ƒscRÒ…÷'BÔ÷væW'2ƒscR¢Ð¢ÆVæ6†W%÷–EöÖWFFFÒ&VBÕ–DÖWFFF¢F6µö'F–f7E÷&ö÷BÒD'F–f7E&ö÷EF€¢F6µöÖöæ—F÷&–æuöF"Ò¦ö–âÕF‚D'F–f7E&ö÷EF‚vÖöæ—F÷&–æræGV6¶F"p¢F6µ÷v÷&¶&Væ6…÷&ö÷BÒ¦ö–âÕF‚D'F–f7E&ö÷EF‚wv÷&¶&Væ6‚p¢F6µ÷6æ6†÷E÷&ö÷BÒ¦ö–âÕF‚D'F–f7E&ö÷EF‚vF6†&ö&E÷6æ6†÷G2p§Ð¥w&—FRÔ§6öäf–ÆR„¦ö–âÕF‚D'F–f7E&ö÷EF‚tTåd•$ôäÔTåBæ§6öâr’FVçf—&öæÖVç@¢FVçdÖBÒ€¢r2v–æF÷w2TBc"Vçf—&öæÖVçBrÂrrÀ¢"Òv–æF÷w3¢B‚FVçf—&öæÖVçBçv–æF÷w2æ6F–öâ–B‚FVçf—&öæÖVçBçv–æF÷w2çfW'6–öâ–'V–ÆBB‚FVçf—&öæÖVçBçv–æF÷w2æ'V–ÆB–"À¢"Ò÷vW%6†VÆÃ¢B‚FVçf—&öæÖVçBç÷vW'6†VÆÂ–"À¢"Ò—F†öã¢B‚FVçf—&öæÖVçBç—F†öâçF‚–òB‚FVçf—&öæÖVçBç—F†öâçfW'6–öâ–"À¢"ÒæöFS¢B‚FVçf—&öæÖVçBææöFRçF‚–òB‚FVçf—&öæÖVçBææöFRçfW'6–öâ–"À¢"ÒçÓ¢B‚FVçf—&öæÖVçBæçÒçF‚–òB‚FVçf—&öæÖVçBæçÒçfW'6–öâ–"À¢"Ò&Wó¢&Wõ&ö÷F"À¢"ÒçfVçc¢B‚FVçf—&öæÖVçBçfVçeöW†—7G2–"À¢"ÒæöFUöÖöGVÆW3¢B‚FVçf—&öæÖVçBææöFUöÖöGVÆW5öW†—7G2–"À¢"Òg&öçFVæBöF—7C¢B‚FVçf—&öæÖVçBæF—7EöW†—7G2–"À¢"ÒF6²&ö÷C¢D'F–f7E&ö÷EF†"À¢rrÀ¢u&÷‡’f&–&ÆW2&R&V6÷&FVBöæÇ’26öæf–wW&VBöæ÷BÖ6öæf–wW&VC²æò7&VFVçF–Ç2&RVÖ—GFVBâp¢¥6WBÔ6öçFVçBÔÆ—FW&ÅF‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚tTåd•$ôäÔTåBæÖBr’ÕfÇVRFVçdÖBÔVæ6öF–ærUDc€ ¢2†6R#¢&÷f–FW"6öææV7F—f—G’ÆFFW"v—F‚&÷VæFVB&WG&–W3²6öçF–çVR÷F†W"v÷&²&Vv&FÆW72à¦f÷"‚FGFV×BÒ²FGFV×BÖÆR´ÖF…Ó£¤Ö‚ƒÂD6öææV7F—f—G”GFV×G2“²FGFV×B²²’°¢bE—F†öâE&÷f–FW%&ö&RÒÖ'F–f7B×&ö÷BD'F–f7E&ö÷EF‚Â÷WBÔ†÷7@¢G&ö&UF‚Ò¦ö–âÕF‚D'F–f7E&ö÷EF‚u$õd”DU%ô4ôääT5D•d•E’æ§6öâp¢–b…FW7BÕF‚ÔÆ—FW&ÅF‚G&ö&UF‚’°¢6÷’Ô—FVÒÔÆ—FW&ÅF‚G&ö&UF‚ÔFW7F–æF–öâ„¦ö–âÕF‚D'F–f7E&ö÷EF‚%$õd”DU%ô4ôääT5D•d•E•ôEDTÕEòFGFV×Bæ§6öâ"’Ôf÷&6P¢G&ö&RÒvWBÔ6öçFVçBÔÆ—FW&ÅF‚G&ö&UF‚Õ&rÔVæ6öF–ærUDc‚Â6öçfW'Dg&öÒÔ§6öà¢G&V6†&ÆRÒ‚G&ö&Rç&÷f–FW'2å4ö&¦V7Bå&÷W'F–W2åfÇVRÂv†W&RÔö&¦V7B²Eòæ6Æ76–f–6F–öâÖWtÄ•dUõ$T4„$ÄRrÒ’ä6÷Vç@¢–b‚G&V6†&ÆRÖwB’²'&V²Ð¢Ð¢–b‚FGFV×BÖÇBD6öææV7F—f—G”GFV×G2’²7F'BÕ6ÆVWÕ6V6öæG2D6öææV7F—f—G•&WG'•6V6öæG2Ð§Ð ¢2†6R3¢vVçV–æR&÷f–FW"ÓâD"Óâv÷&¶&Væ6…'VâÓâæ÷&ÖÂ6æ6†÷B4Ä’à¢bE—F†ööâE&VÅ6æ6†÷DG&—fW"ÒÖ'F–f7B×&ö÷BD'F–f7E&ö÷EF‚Â÷WBÔ†÷7@¢G&VÅF‚Ò¦ö–âÕF‚D'F–f7E&ö÷EF‚u$TÅõ4ä4„õEõTBæ§6öâp¢G&VÂÒ–b…FW7BÕF‚ÔÆ—FW&ÅF‚G&VÅF‚’²vWBÔ6öçFVçBÔÆ—FW&ÅF‚G&VÅF‚Õ&rÔVæ6öF–ærUDc‚Â6öçfW'Dg&öÒÔ§6öâÒVÇ6R²FçVÆÂÐ¢FW‡V7FVE6æ6†÷D–BÒ–b‚G&VÂÖæBG&VÂç6æ6†÷B’²·7G&–æuÒG&VÂç6æ6†÷Bç6æ6†÷Eö–BÒVÇ6R²FçVÆÂÐ¢FW‡V7FVE'Vä–BÒ–b‚G&VÂÖæBG&VÂç6æ6†÷B’²·7G&–æuÒG&VÂç6æ6†÷Bç'Våö–BÒVÇ6R²FçVÆÂÐ¢FW‡V7FVEFV6†æ–6Ä6÷VçBÒ–b‚G&VÂÖæBG&VÂç6æ6†÷B’²¶–çEÒG&VÂç6æ6†÷BçFV6†æ–6Åö†—7F÷'•ö6÷VçBÒVÇ6R²FçVÆÂÐ¢FW‡V7FVD6æöæ–6Ä6÷VçBÒ–b‚G&VÂÖæBG&VÂç6æ6†÷B’²¶–çEÒG&VÂç6æ6†÷Bæ6æöæ–6Åö†—7F÷'•ö6÷VçBÒVÇ6R²FçVÆÂÐ¢EF6µ6æ6†÷E&ö÷BÒ–b‚G&VÂÖæBG&VÂçF‡2ç6æ6†÷E÷&ö÷B’²·7G&–æuÒG&VÂçF‡2ç6æ6†÷E÷&ö÷BÒVÇ6R²¦ö–âÕF‚D'F–f7E&ö÷EF‚vF6†&ö&E÷6æ6†÷G2rÐ¢FVçc¤Ô5$õõtõ$´$Tä4…õ4ä4„õEõ$ôõBÒEF6µ6æ6†÷E&ö÷@¢FVçc¤Ô5$õõtõ$´$Tä4…ôäõô%$õu4U"Òsp ¦–b‚Öæ÷BFW‡V7FVE6æ6†÷D–B’°¢G&÷f–FW%&ö&RÒ–b…FW7BÕF‚ÔÆ—FW&ÅF‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚u$õd”DU%ô4ôääT5D•d•E’æ§6öâr’’²vWBÔ6öçFVçBÔÆ—FW&ÅF‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚u$õd”DU%ô4ôääT5D•d•E’æ§6öâr’Õ&rÔVæ6öF–ærUDc‚Â6öçfW'Dg&öÒÔ§6öâÒVÇ6R²FçVÆÂÐ¢F6Æ76W2Ò–b‚G&÷f–FW%&ö&R’²‚G&÷f–FW%&ö&Rç&÷f–FW'2å4ö&¦V7Bå&÷W'F–W2åfÇVRÂf÷$V6‚Ôö&¦V7B²Eòæ6Æ76–f–6F–öâÒ’ÒVÇ6R²‚’Ð¢D&Æö6¶W'2äFB…·67W7FöÖö&¦V7EÔ²6Æ72Òu$TÅõ$õd”DU%ôU…DU$äÅô$Äô4´U"s²66Væ&–òÒw&VÂ×6æ6†÷Bs²FWF–ÂÒ$æòW'6—7FVB&VÂ6æ6†÷C²&÷f–FW"6Æ76W3ÒB‚F6Æ76W2Ö¦ö–ârÂr’"Ò§Ð ¢G—F†öå6VçF–æVÂÒ7F'BÕ6VçF–æVÂw—F†öâp¢FæöFU6VçF–æVÂÒ7F'BÕ6VçF–æVÂvæöFRp §G'’°¢26ÆVâ7F'Bà¢·fö–EÒ„–çfö¶RÕ7F÷6öFR¢F&Vf÷&RÒ6æ6†÷BÕ7FFP¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FgFW"Ò6æ6†÷BÕ7FFP¢&V6÷&BÕ66Væ&–òv6ÆVâ×7F'Br‚F6öFRÖWÖæBFgFW"æ†VÇF…÷7FGW2ÖW#’&W†—CÒF6öFR†VÇFƒÒB‚FgFW"æ†VÇF…÷7FGW2’"tÄ”dT5”4ÄRrF&Vf÷&RFgFW  ¢2’÷7FF–2&÷‡’ÇW2vVçV–æR6æ6†÷Bv†Vâf–Æ&ÆRà¢Fg&öçD†VÇF‚ÒW&ÂÕ&W7VÇB"DW&Âõõö†VÇF‚ ¢F–æFW‚ÒW&ÂÕ&W7VÇB"DW&Âò ¢G&÷‡”†VÇF‚ÒW&ÂÕ&W7VÇB"DW&Âö’ö†VÇF‚ ¢&V6÷&BÕ66Væ&–òv'V–ÇBÖg&öçFVæB×7FF–2×&÷‡’r‚Fg&öçD†VÇF‚ç7FGW2ÖW#ÖæBF–æFW‚ç7FGW2ÖW#ÖæBG&÷‡”†VÇF‚ç7FGW2ÖW#’&g&öçFVæCÒB‚Fg&öçD†VÇF‚ç7FGW2’–æFWƒÒB‚F–æFW‚ç7FGW2’&÷‡“ÒB‚G&÷‡”†VÇF‚ç7FGW2’ ¢–b‚FW‡V7FVE6æ6†÷D–B’°¢G7FFRÒ6æ6†÷BÕ7FFP¢G6ÖRÒG7FFRç6æ6†÷Eö–BÖWFW‡V7FVE6æ6†÷D–BÖæBG7FFRç'Våö–BÖWFW‡V7FVE'Vä–@¢&V6÷&BÕ66Væ&–òw&VÂ×6æ6†÷BÖ’×&VF&6²rG6ÖR&W‡V7FVCÒFW‡V7FVE6æ6†÷D–B7GVÃÒB‚G7FFRç6æ6†÷Eö–B’'VãÒB‚G7FFRç'Våö–B’ ¢F†—7E6ÖRÒ‚G7FFRçFV6†æ–6Åö†—7F÷'•ö6÷VçBÖWFW‡V7FVEFV6†æ–6Ä6÷VçBÖæBG7FFRæ6æöæ–6Åö†—7F÷'•ö6÷VçBÖWFW‡V7FVD6æöæ–6Ä6÷VçB¢&V6÷&BÕ66Væ&–òwW'6—7FVBÖ†—7F÷'’Ö’×&VF&6²rF†—7E6ÖR'FV6†æ–6ÃÒB‚G7FFRçFV6†æ–6Åö†—7F÷'•ö6÷VçB’òFW‡V7FVEFV6†æ–6Ä6÷VçB6æöæ–6ÃÒB‚G7FFRæ6æöæ–6Åö†—7F÷'•ö6÷VçB’òFW‡V7FVD6æöæ–6Ä6÷VçB ¢Ð ¢2&VÂ'&÷w6W"ÆVæ6‚æB'&÷w6W"ÖVæv–æRDôÒ&VF&6²à¢G'’°¢7F'BÕ&ö6W72DW&ÂÂ÷WBÔçVÆÀ¢&V6÷&BÕ66Væ&–òwv–æF÷w2ÖFVfVÇBÖ'&÷w6W"Ö÷VârGG'VR&÷VæVBDW&Â"t%$õu4T"p¢Ò6F6‚°¢&V6÷&BÕ66Væ&–òwv–æF÷w2ÖFVfVÇBÖ'&÷w6W"Ö÷VârFfÇ6REòäW†6WF–öâäÖW76vRt%$õu4U"p¢Ð¢–b‚FW‡V7FVE'Vä–B’°¢F'&÷w6W$6†V6²Ò'&÷w6W"ÔFöÒÔ6†V6²FW‡V7FVE'Vä–@¢&V6÷&BÕ66Væ&–òwv–æF÷w2Ö'&÷w6W"Öæ÷&ÖÂÖÖöFR×&VF&6²rF'&÷w6W$6†V6²ç72F'&÷w6W$6†V6²æFWF–Ât%$õu4T"p¢–b‚Öæ÷BF'&÷w6W$6†V6²æGFV×FVB’²D&Æö6¶W'2äFB…·67W7FöÖö&¦V7EÔ²6Æ72ÒtäD•dUô%$õu4U%ôUDôÔD”ôåô$Äô4´TBs²66Væ&–òÒwv–æF÷w2Ö'&÷w6W"Öæ÷&ÖÂÖÖöFR×&VF&6²s²FWF–ÂÒF'&÷w6W$6†V6²æFWF–ÂÒ’Ð¢Ð ¢2GWÆ–6FR7F'B×W7B&WW6RöæR†VÇF‡’÷væVB7F6²à¢FÖWF&Vf÷&RÒ&VBÕ–DÖWFFF¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FÖWFgFW"Ò&VBÕ–DÖWFFF¢G6ÖU–G2ÒFÖWF&Vf÷&RÖæBFÖWFgFW"ÖæBFÖWF&Vf÷&Ræ&6¶VæBç–BÖWFÖWFgFW"æ&6¶VæBç–BÖæBFÖWF&Vf÷&Ræg&öçFVæBç–BÖWFÖWFgFW"æg&öçFVæBç–@¢&V6÷&BÕ66Væ&–òvGWÆ–6FR×7F'BÖFWFW&Ö–æ—7F–2r‚F6öFRÖWÖæBG6ÖU–G2’&W†—CÒF6öFR&6¶VæCÒB‚FÖWFgFW"æ&6¶VæBç–B’g&öçFVæCÒB‚FÖWFgFW"æg&öçFVæBç–B’"u$ô4U55ôõtäU%4„•p ¢25Dõ¶–ÆÇ2öæÇ’ÆVæ6†W"Ö÷væVB7F6³²Vç&VÆFVB—F†öâôæöFR6VçF–æVÇ27W'f—fRà¢F6öFRÒ–çfö¶RÕ7F÷6öFP¢G6VçF–æVÇ4Æ—fRÒ…6VçF–æVÂÔÆ—fRG—F†öå6VçF–æVÂ’ÖæB…6VçF–æVÂÔÆ—fRFæöFU6VçF–æVÂ¢G÷'G4F÷vâÒ…v—BÕ÷'DF÷vâD&6¶VæE÷'B’ÖæB…v—BÕ÷'DF÷vâDg&öçFVæE÷'B¢&V6÷&BÕ66Væ&–òw7F÷Ö÷væVBÖöæÇ’×Vç&VÆFVB×7W'f—fRr‚F6öFRÖWÖæBG6VçF–æVÇ4Æ—fRÖæBG÷'G4F÷vâ’&W†—CÒF6öFR6VçF–æVÇ3ÒG6VçF–æVÇ4Æ—fR÷'G4F÷vãÒG÷'G4F÷vâ"u$ô4U55ôõtäU%4„•p ¢2gVÆÂ7F6²&W7F'B×W7B&VBW†7FÇ’F†R6ÖRW'6—7FVB6æ6†÷Bö†—7F÷'’æBf'&–6FRæ÷F†–ærà¢F&Vf÷&RÒ6æ6†÷BÕ7FFP¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FgFW"Ò6æ6†÷BÕ7FFP¢G6ÖU6æ6†÷BÒ–b‚FW‡V7FVE6æ6†÷D–B’²FgFW"ç6æ6†÷Eö–BÖWFW‡V7FVE6æ6†÷D–BÒVÇ6R²FgFW"æÆFW7E÷7FGW2ÖWCBÐ¢G6ÖT†—7F÷'’Ò–b‚FW‡V7FVE6æ6†÷D–B’²FgFW"çFV6†æ–6Åö†—7F÷'•ö6÷VçBÖWFW‡V7FVEFV6†æ–6Ä6÷VçBÖæBFgFW"æ6æöæ–6Åö†—7F÷'•ö6÷VçBÖWFW‡V7FVD6æöæ–6Ä6÷VçBÒVÇ6R²GG'VRÐ¢&V6÷&BÕ66Væ&–òvgVÆÂ×7F6²×&W7F'B×6ÖR×W'6—7FVB×7FFRr‚F6öFRÖWÖæBG6ÖU6æ6†÷BÖæBG6ÖT†—7F÷'’’&W†—CÒF6öFR6æ6†÷CÒB‚FgFW"ç6æ6†÷Eö–B’FV6†æ–6ÃÒB‚FgFW"çFV6†æ–6Åö†—7F÷'•ö6÷VçB’6æöæ–6ÃÒB‚FgFW"æ6æöæ–6Åö†—7F÷'•ö6÷VçB’"tÄ”dT5”4ÄRrF&Vf÷&RFgFW  ¢2’ÖöæÇ’7&6ƒ¢ÆVæ6†W"Ö’&V7–6ÆRöæÇ’fW&–f–VB÷væVB'F–Â7F6²ÂF†Vâ×W7B&W7F÷&R7FFRà¢FÖWFÒ&VBÕ–DÖWFFF¢–b‚FÖWFÖæBFÖWFæ&6¶VæBç–B’²7F÷Õ&ö6W72Ô–B…¶–çEÒFÖWFæ&6¶VæBç–B’Ôf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVS²7F'BÕ6ÆVWÔÖ–ÆÆ—6V6öæG2sÐ¢G'F–ÂÒ6æ6†÷BÕ7FFP¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢G&V6÷fW&VBÒ6æ6†÷BÕ7FFP¢Fö²ÒF6öFRÖWÖæBG&V6÷fW&VBæ†VÇF…÷7FGW2ÖW#ÖæB‚‚Öæ÷BFW‡V7FVE6æ6†÷D–B’Ö÷"G&V6÷fW&VBç6æ6†÷Eö–BÖWFW‡V7FVE6æ6†÷D–B¢&V6÷&BÕ66Væ&–òv’ÖöæÇ’Ö7&6‚×&V6÷fW'’rFö²&W†—CÒF6öFR&V6÷fW&VE6æ6†÷CÒB‚G&V6÷fW&VBç6æ6†÷Eö–B’"u$ô4U55ôõtäU%4„•rG'F–ÂG&V6÷fW&V@ ¢2g&öçFVæBÖöæÇ’7&6‚à¢FÖWFÒ&VBÕ–DÖWFFF¢–b‚FÖWFÖæBFÖWFæg&öçFVæBç–B’²7F÷Õ&ö6W72Ô–B…¶–çEÒFÖWFæg&öçFVæBç–B’Ôf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVS²7F'BÕ6ÆVWÔÖ–ÆÆ—6V6öæG2sÐ¢G'F–ÂÒ6æ6†÷BÕ7FFP¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢G&V6÷fW&VBÒ6æ6†÷BÕ7FFP¢Fö²ÒF6öFRÖWÖæBG&V6÷fW&VBæ†VÇF…÷7FGW2ÖW#ÖæB‚‚Öæ÷BFW‡V7FVE6æ6†÷D–B’Ö÷"G&V6÷fW&VBç6æ6†÷Eö–BÖWFW‡V7FVE6æ6†÷D–B¢&V6÷&BÕ66Væ&–òvg&öçFVæBÖöæÇ’Ö7&6‚×&V6÷fW'’rFö²&W†—CÒF6öFR&V6÷fW&VE6æ6†÷CÒB‚G&V6÷fW&VBç6æ6†÷Eö–B’"u$ô4U55ôõtäU%4„•rG'F–ÂG&V6÷fW&V@ ¢2f÷&6VBFW&Ö–æF–öâöb&÷F‚÷væVB&ö6W76W2ÆVfW27FÆRÖWFFF²æW‡B7F'B×W7B6ÆVâ&V6÷fW"à¢FÖWFÒ&VBÕ–DÖWFFF¢f÷&V6‚‚FVçG'’–â‚FÖWFæ&6¶VæBÂFÖWFæg&öçFVæB’’²–b‚FVçG'’ÖæBFVçG'’ç–B’²7F÷Õ&ö6W72Ô–B…¶–çEÒFVçG'’ç–B’Ôf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVRÒÐ¢7F'BÕ6ÆVWÔÖ–ÆÆ—6V6öæG2s ¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FgFW"Ò6æ6†÷BÕ7FFP¢&V6÷&BÕ66Væ&–òvf÷&6VBÖ÷væVB×FW&Ö–æF–öâ×&V6÷fW'’r‚F6öFRÖWÖæBFgFW"æ†VÇF…÷7FGW2ÖW#’&W†—CÒF6öFR†VÇFƒÒB‚FgFW"æ†VÇF…÷7FGW2’"u$ô4U55ôõtäU%4„•p ¢2Ö—76–ærÖWFFFv†–ÆRÆ—fS¢5Dõ×W7Bf–Â6Æ÷6VBæBÆVfR&ö6W76W2'Vææ–æs²&W7F÷&RWf–FVæ6RF†Vâ7F÷æ÷&ÖÆÇ’à¢FÖWF&rÒ–b…FW7BÕF‚ÔÆ—FW&ÅF‚E–Df–ÆR’²vWBÔ6öçFVçBÔÆ—FW&ÅF‚E–Df–ÆRÕ&rÔVæ6öF–ærUDc‚ÒVÇ6R²FçVÆÂÐ¢–b‚FÖWF&r’°¢&VÖ÷fRÔ—FVÒÔÆ—FW&ÅF‚E–Df–ÆRÔf÷&6P¢F6öFRÒ–çfö¶RÕ7F÷6öFP¢G7F–ÆÅWÒ…W&ÂÕ&W7VÇB"DW&Âõõö†VÇF‚"’ç7FGW2ÖW# ¢&V6÷&BÕ66Væ&–òvÖ—76–ærÖÖWFFF×7F÷Öf–Æ6Æ÷6VBr‚F6öFRÖWCÖæBG7F–ÆÅW’&W†—CÒF6öFR7F–ÆÅWÒG7F–ÆÅW"u$ô4U55ôõtäU%4„•p¢6WBÔ6öçFVçBÔÆ—FW&ÅF‚E–Df–ÆRÕfÇVRFÖWF&rÔVæ6öF–ærUDc€¢·fö–EÒ„–çfö¶RÕ7F÷6öFR¢Ð ¢27FÆR”BÖWFFFv—F‚æòÆ—fR÷væVB&ö6W72×W7B&RF—66&FVB6fVÇ’BæW‡B7F'Bà¢G7FÆRÒ²7&VFVEöBÒ„vWBÔFFR’åFõ7G&–ær‚vòr“²&Wõ÷&ö÷BÒE&Wõ&ö÷C²&6¶VæBÒ·–CÓ#CsCƒ3·÷'CÓƒ‡Ó²g&öçFVæCÔ·–CÓ#CsCƒ3#·÷'CÓƒscWÒÐ¢w&—FRÔ§6öäf–ÆRE–Df–ÆRG7FÆP¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FgFW"Ò6æ6†÷BÕ7FFP¢&V6÷&BÕ66Væ&–òw7FÆR×–BÖÖWFFF×&V6÷fW'’r‚F6öFRÖWÖæBFgFW"æ†VÇF…÷7FGW2ÖW#’&W†—CÒF6öFR†VÇFƒÒB‚FgFW"æ†VÇF…÷7FGW2’"u$ô4U55ôõtäU%4„•p ¢26÷''WBÖWFFFv†–ÆRÆ—fS¢5Dõ×W7B&W6W'fR6fWG’æB&VgW6RFò¶–ÆÂVæ¶æ÷vâ÷væW'6†—à¢FÖWF&rÒvWBÔ6öçFVçBÔÆ—FW&ÅF‚E–Df–ÆRÕ&rÔVæ6öF–ærUDc€¢6WBÔ6öçFVçBÔÆ—FW&ÅF‚E–Df–ÆRÕfÇVRw¶6÷''WFVBÖ§6öârÔVæ6öF–ærUDc€¢F6öFRÒ–çfö¶RÕ7F÷6öFP¢G7F–ÆÅWÒ…W&ÂÕ&W7VÇB"DW&Âõõö†VÇF‚"’ç7FGW2ÖW# ¢&V6÷&BÕ66Væ&–òv6÷''WBÖÖWFFF×7F÷Öf–Æ6Æ÷6VBr‚F6öFRÖWC2ÖæBG7F–ÆÅW’&W†—CÒF6öFR7F–ÆÅWÒG7F–ÆÅW"u$ô4U55ôõtäU%4„•p¢6WBÔ6öçFVçBÔÆ—FW&ÅF‚E–Df–ÆRÕfÇVRFÖWF&rÔVæ6öF–ærUDc€¢·fö–EÒ„–çfö¶RÕ7F÷6öFR ¢2f÷&V–vâ&6¶VæBö67WçB×W7B7W'f—fRÆVæ6†W"&VgW6Âà¢Ff÷&V–vä&6¶VæBÒ7F'BÔf÷&V–vå÷'BD&6¶VæE÷'@¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FÆ—fRÒ¶&ööÅÒ„vWBÕ&ö6W72Ô–BFf÷&V–vä&6¶VæBä–BÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVR¢&V6÷&BÕ66Væ&–òvf÷&V–vâÖ&6¶VæB×÷'BÖf–Æ6Æ÷6VBr‚F6öFRÖWBÖæBFÆ—fR’&W†—CÒF6öFRf÷&V–väÆ—fSÒFÆ—fR"u$ô4U55ôõtäU%4„•p¢–b‚FÆ—fR’²7F÷Õ&ö6W72Ô–BFf÷&V–vä&6¶VæBä–BÔf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVRÐ¢7F'BÕ6ÆVWÔÖ–ÆÆ—6V6öæG2S  ¢2f÷&V–vâg&öçFVæBö67WçB×W7BÇ6ò7W'f—fRà¢Ff÷&V–väg&öçFVæBÒ7F'BÔf÷&V–vå÷'BDg&öçFVæE÷'@¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FÆ—fRÒ¶&ööÅÒ„vWBÕ&ö6W72Ô–BFf÷&V–väg&öçFVæBä–BÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVR¢&V6÷&BÕ66Væ&–òvf÷&V–vâÖg&öçFVæB×÷'BÖf–Æ6Æ÷6VBr‚F6öFRÖW2ÖæBFÆ—fR’&W†—CÒF6öFRf÷&V–väÆ—fSÒFÆ—fR"u$ô4U55ôõtäU%4„•p¢–b‚FÆ—fR’²7F÷Õ&ö6W72Ô–BFf÷&V–väg&öçFVæBä–BÔf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVRÐ¢7F'BÕ6ÆVWÔÖ–ÆÆ—6V6öæG2S  ¢2Ö—76–ær6æ6†÷B×W7B&VÖ–âVæf–Æ&ÆRÂæWfW"FVÖòöf'&–6FVBà¢FV×G•&ö÷BÒ¦ö–âÕF‚D'F–f7E&ö÷EF‚vV×G•÷6æ6†÷G5öf÷%öæVvF—fU÷VBp¢æWrÔ—FVÒÔ—FVÕG—RF—&V7F÷'’Ôf÷&6RÕF‚FV×G•&ö÷BÂ÷WBÔçVÆÀ¢FVçc¤Ô5$õõtõ$´$Tä4…õ4ä4„õEõ$ôõBÒFV×G•&ö÷@¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢FÆFW7BÒW&ÂÕ&W7VÇB"DW&Âö’÷6æ6†÷BöÆFW7B ¢F†—7F÷'’Ò§6öâÕW&Â"DW&Âö’÷6æ6†÷G2 ¢FæVvF—fU72ÒF6öFRÖWÖæBFÆFW7Bç7FGW2ÖWCBÖæBF†—7F÷'’ç7FGW2ÖW#ÖæB‚F†—7F÷'’æ§6öâæ†—7F÷'’’ä6÷VçBÖW ¢&V6÷&BÕ66Væ&–òvÖ—76–ær×6æ6†÷B×Væf–Æ&ÆRÖæòÖFVÖòrFæVvF—fU72&W†—CÒF6öFRÆFW7CÒB‚FÆFW7Bç7FGW2’†—7F÷'“ÒB‚F†—7F÷'’ç7FGW2’6÷VçCÒB„‚F†—7F÷'’æ§6öâæ†—7F÷'’’ä6÷VçB’ ¢·fö–EÒ„–çfö¶RÕ7F÷6öFR ¢2&W7F÷&RW'6—7FVB&ö÷BæB&÷fR6ÖR7FFRöæRf–æÂF–ÖRà¢FVçc¤Ô5$õõtõ$´$Tä4…õ4ä4„õEõ$ôõBÒEF6µ6æ6†÷E&ö÷@¢F6öFRÒ–çfö¶RÔÆVæ6†W$6öFP¢Ff–æÅ7FFRÒ6æ6†÷BÕ7FFP¢G6ÖU6æ6†÷BÒ–b‚FW‡V7FVE6æ6†÷D–B’²Ff–æÅ7FFRç6æ6†÷Eö–BÖWFW‡V7FVE6æ6†÷D–BÒVÇ6R²Ff–æÅ7FFRæÆFW7E÷7FGW2ÖWCBÐ¢G6ÖT†—7F÷'’Ò–b‚FW‡V7FVE6æ6†÷D–B’²Ff–æÅ7FFRçFV6†æ–6Åö†—7F÷'•ö6÷VçBÖWFW‡V7FVEFV6†æ–6Ä6÷VçBÖæBFf–æÅ7FFRæ6æöæ–6Åö†—7F÷'•ö6÷VçBÖWFW‡V7FVD6æöæ–6Ä6÷VçBÒVÇ6R²GG'VRÐ¢&V6÷&BÕ66Væ&–òvf–æÂ×&W7F'B×&VF&6²ÖæòÖæWrÖV6öæöÖ–2×vVV²r‚F6öFRÖWÖæBG6ÖU6æ6†÷BÖæBG6ÖT†—7F÷'’’'6æ6†÷CÒB‚Ff–æÅ7FFRç6æ6†÷Eö–B’FV6†æ–6ÃÒB‚Ff–æÅ7FFRçFV6†æ–6Åö†—7F÷'•ö6÷VçB’6æöæ–6ÃÒB‚Ff–æÅ7FFRæ6æöæ–6Åö†—7F÷'•ö6÷VçB’ ¢·fö–EÒ„–çfö¶RÕ7F÷6öFR§Ð¦f–æÆÇ’°¢f÷&V6‚‚G–âDf÷&V–vå&ö6W76W2’²–b„vWBÕ&ö6W72Ô–BGä–BÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVR’²7F÷Õ&ö6W72Ô–BGä–BÔf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVRÒÐ¢f÷&V6‚‚G–âE6VçF–æVÇ2’²–b„vWBÕ&ö6W72Ô–BGä–BÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVR’²7F÷Õ&ö6W72Ô–BGä–BÔf÷&6RÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVRÒÐ¢&VÖ÷fRÔ—FVÒVçc¤Ô5$õõtõ$´$Tä4…ôäõô%$õu4U"ÔW'&÷$7F–öâ6–ÆVçFÇ”6öçF–çVP§Ð ¥w&—FRÔ§6öäf–ÆR„¦ö–âÕF‚D'F–f7E&ö÷EF‚u4ôµôÔE$•‚æ§6öâr’‚E6ö²¥w&—FRÔÖ&¶F÷väÖG&—‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚u4ôµôÔE$•‚æÖBr’uv–æF÷w26ö²ÖG&—‚c"r‚E6ö²¥w&—FRÔ§6öäf–ÆR„¦ö–âÕF‚D'F–f7E&ö÷EF‚u$ô4U55ôõtäU%4„•ôÔE$•‚æ§6öâr’‚D÷væW'6†—¥w&—FRÔÖ&¶F÷väÖG&—‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚u$ô4U55ôõtäU%4„•ôÔE$•‚æÖBr’u&ö6W72÷væW'6†—ÖG&—‚c"r‚D÷væW'6†—¥w&—FRÔ§6öäf–ÆR„¦ö–âÕF‚D'F–f7E&ö÷EF‚t$Äô4´U%ôÄTDtU"æ§6öâr’‚D&Æö6¶W'2¢F&Æö6¶W$ÖBÒæWrÔö&¦V7B7—7FVÒä6öÆÆV7F–öç2ävVæW&–2äÆ—7E·7G&–æuÐ¢F&Æö6¶W$ÖBäFB‚r2&Æö6¶W"ÆVFvW"c"r“²F&Æö6¶W$ÖBäFB‚rr¦–b‚D&Æö6¶W'2ä6÷VçBÖW’²F&Æö6¶W$ÖBäFB‚rÒäôäRr’Ð¦VÇ6R²f÷&V6‚‚F"–âD&Æö6¶W'2’²F&Æö6¶W$ÖBäFB‚"Ò¢¢B‚F"æ6Æ72’¢¢òB‚F"ç66Væ&–ò–¢B‚F"æFWF–Â’"’ÒÐ¥6WBÔ6öçFVçBÔÆ—FW&ÅF‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚t$Äô4´U%ôÄTDtU"æÖBr’ÕfÇVRF&Æö6¶W$ÖBÔVæ6öF–ærUDc€ ¢Ff–ÆVE66Væ&–÷2Ò‚E6ö²Âv†W&RÔö&¦V7B²Öæ÷BEòç72Ò¢F6ä6ö×ÆWFRÒFW‡V7FVE6æ6†÷D–BÖæBFf–ÆVE66Væ&–÷2ä6÷VçBÖWÖæBD&Æö6¶W'2ä6÷VçBÖW ¢F†æFöfe7FGW2Ò–b‚F6ä6ö×ÆWFR’²t„äDôdeô4ôÕÄUDS¢Äô4ÂÔ"Õt”äDõu2Õ$TÂÕ4ä4„õBÕ4ô²ÕTBÕc"rÒVÇ6V–b‚Öæ÷BFW‡V7FVE6æ6†÷D–B’²u$TÅõ$õd”DU%ôU…DU$äÅô$Äô4´U"rÒVÇ6R²täD•dUõt”äDõu5õTEô$Äô4´TBrÐ¢F†æFöfbÒ€¢r2Äô4ÂÔ"v–æF÷w2&VÂ6æ6†÷B6ö²TBc"†æFöfbrÂrrÀ¢%7FGW3¢¢¢F†æFöfe7FGW2¢¢"ÂrrÀ¢"Ò&6Rö7W'&VçB'&æ6‚W†V7WF–öâ×W7B&R&÷VæBFòF†R3Cg&W6‚Ö&6R6öÖÖ—Bâ"À¢"Ò&VÂ6æ6†÷B–C¢B†–b‚FW‡V7FVE6æ6†÷D–B’²FW‡V7FVE6æ6†÷D–GÒVÇ6R²täôäRwÒ–"À¢"ÒW‡V7FVB'Vâ–C¢B†–b‚FW‡V7FVE'Vä–B’²FW‡V7FVE'Vä–GÒVÇ6R²täôäRwÒ–"À¢"Ò6ö²66Væ&–÷3¢B‚E6ö²ä6÷VçB–òf–ÆVC¢B‚Ff–ÆVE66Væ&–÷2ä6÷VçB–"À¢"Ò&Æö6¶W"ÆVFvW"VçG&–W3¢B‚D&Æö6¶W'2ä6÷VçB–"À¢rÒæòf—‡GW&RöFVÖòfÆÆ&6²—266WFVB2&VÂTBWf–FVæ6RârÀ¢rÒæòÖW&vR—2W&f÷&ÖVB'’F†—267&—BârÀ¢rp¢¥6WBÔ6öçFVçBÔÆ—FW&ÅF‚„¦ö–âÕF‚D'F–f7E&ö÷EF‚t„äDôdbæÖBr’ÕfÇVRF†æFöfbÔVæ6öF–ærUDc€¥w&—FRÔ†÷7B$d”äÅõ5DEU3ÒF†æFöfe7FGW2 ¦W†—BB†–b‚F6ä6ö×ÆWFR’²ÒVÇ6R²"Ò 