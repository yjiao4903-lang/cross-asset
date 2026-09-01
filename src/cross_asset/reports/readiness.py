"""Deterministic data/history readiness summary."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def generate_readiness(store, output_dir="artifacts/readiness"):
    observations = store.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    registry = store.conn.execute("SELECT COUNT(*) FROM data_acceptance_registry WHERE status='PASS'").fetchone()[0]
    ready = observations > 0 and registry > 0
    payload = {"generated_at": datetime.now(UTC).isoformat(), "status": "DATA_READY" if ready else "DATA_BLOCKED", "observations": observations, "accepted_pass": registry, "pit_admissible": ready}
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    for name, body in (("DATA_READY", payload), ("HISTORY_READY", {**payload, "status": "HISTORY_READY" if ready else "HISTORY_BLOCKED"})):
        text = json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        tmp = out / f".{name}.tmp"; tmp.write_text(text, encoding="utf-8"); tmp.replace(out / f"{name}.json")
        tmp = out / f".{name}.md"; tmp.write_text(f"# {name}\n\n```json\n{text}```\n", encoding="utf-8"); tmp.replace(out / f"{name}.md")
    return payload
