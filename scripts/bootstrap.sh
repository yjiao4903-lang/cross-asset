#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/raw data/db data/manual_inbox data/manual_archive artifacts
if [[ "${SKIP_INSTALL:-0}" != "1" ]] && command -v uv >/dev/null 2>&1; then uv sync; fi
echo "Cross-asset engine workspace initialized."

