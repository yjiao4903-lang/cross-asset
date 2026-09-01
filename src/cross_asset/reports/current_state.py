"""Generated current project state; replaces manually copied counters."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def _git(root: Path) -> dict:
    def run(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )

    head = run("rev-parse", "HEAD")
    status = run("status", "--short")
    tags = run("tag", "--points-at", "HEAD")
    return {
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()),
        "changed_paths": [line[3:] for line in status.stdout.splitlines() if len(line) > 3],
        "head_tags": [line for line in tags.stdout.splitlines() if line],
    }


def _tests(root: Path) -> dict:
    basetemp = root / ".tmp" / "current-state-tests"
    completed = subprocess.run(
        [
            str(root / ".venv" / "Scripts" / "python.exe"),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(basetemp),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = (completed.stdout + completed.stderr).strip().splitlines()[-5:]
    return {"exit_code": completed.returncode, "passed": completed.returncode == 0, "tail": tail}


def generate_current_state(store, *, root=".", output="artifacts/current_state/generated", run_tests=False):
    root_path = Path(root).resolve()
    tables = [row[0] for row in store.conn.execute("SHOW TABLES").fetchall()]
    counts = {table: store.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git": _git(root_path),
        "database_counts": counts,
        "latest_local_experiment": store.conn.execute(
            """SELECT run_id,status,decision_time,data_snapshot_id,run_mode,universe_status,
                      requested_assets,available_assets,excluded_assets,idempotency_key
               FROM model_runs WHERE run_mode='LOCAL_EXPERIMENT'
               ORDER BY started_at DESC LIMIT 1"""
        ).fetchone(),
        "tests": _tests(root_path) if run_tests else {"status": "NOT_RUN"},
    }
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "CURRENT_STATE.json").write_text(
        json.dumps(payload, ensure_ascii=False, default=str, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Generated Current State",
        "",
        f"Generated at: {payload['generated_at']}",
        f"Git HEAD: `{payload['git']['head']}`",
        f"Git dirty: `{payload['git']['dirty']}`",
        "",
        "## Database counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
        *[f"| {name} | {value} |" for name, value in sorted(counts.items())],
        "",
        "## Tests",
        "",
        "```json",
        json.dumps(payload["tests"], ensure_ascii=False, default=str, indent=2),
        "```",
    ]
    (output_path / "CURRENT_STATE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


__all__ = ["generate_current_state"]
