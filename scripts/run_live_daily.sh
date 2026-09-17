#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-src}"
WORKBENCH_ROOT="${CROSS_ASSET_WORKBENCH_ROOT:-artifacts/workbench}"
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY="${PYTHON:-python3}"
fi
"$PY" -m cross_asset.cli shadow-run --source-mode LIVE --workbench-root "$WORKBENCH_ROOT"
