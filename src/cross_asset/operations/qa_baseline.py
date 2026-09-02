"""Canonical local QA baseline artifact generator."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ..storage.provenance import code_version, config_hash


def _run(command: list[str], root: Path) -> dict[str, object]:
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    return {"exit_code": result.returncode, "passed": result.returncode == 0, "output_tail": (result.stdout + result.stderr)[-500:]}


def generate_qa_baseline(root: str | Path = ".", output_dir: str | Path = "artifacts/qa") -> dict[str, object]:
    root, output_dir = Path(root), Path(output_dir)
    python = sys.executable
    with tempfile.TemporaryDirectory(
        prefix="cross-asset-pytest-",
        ignore_cleanup_errors=True,
    ) as basetemp:
        pytest = _run(
            [
                python,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                basetemp,
            ],
            root,
        )
    match = re.search(r"(\d+) passed", str(pytest["output_tail"]))
    payload = {"generated_at": datetime.now(UTC).isoformat(), "code_version": code_version(root), "pytest": {**pytest, "passed_count": int(match.group(1)) if match else None}, "ruff": _run([python, "-m", "ruff", "check", "src", "tests"], root), "compileall": _run([python, "-m", "compileall", "-q", "src"], root), "config_hash": config_hash([root / "config/sources.yml", root / "config/research.yml", root / "config/decision_time.yml"])}
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix, content in (("json", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"), ("md", "# QA Baseline\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n```\n")):
        tmp = output_dir / f".latest.{suffix}.tmp"
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(output_dir / f"latest.{suffix}")
    return payload
