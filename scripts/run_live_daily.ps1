$env:PYTHONPATH = if ($env:PYTHONPATH) { $env:PYTHONPATH } else { "src" }
$workbench = if ($env:CROSS_ASSET_WORKBENCH_ROOT) { $env:CROSS_ASSET_WORKBENCH_ROOT } else { "artifacts/workbench" }
$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $python -m cross_asset.cli shadow-run --source-mode LIVE --workbench-root $workbench
exit $LASTEXITCODE
