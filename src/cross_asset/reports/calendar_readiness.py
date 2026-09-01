from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml


def generate_calendar_readiness(config_path="config/calendars.yml", output_dir="artifacts/readiness"):
    calendars = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")).get("calendars", {})
    markets = []
    for name in sorted(calendars):
        item = calendars[name]
        markets.append({"calendar_id": item.get("calendar_id", name), "status": "CALENDAR_READY" if item.get("verified") is True and item.get("capability_status") == "VERIFIED" else "UNKNOWN", "blockers": [] if item.get("verified") is True else ["verified_calendar_evidence_missing", "reviewer_approval_missing"]})
    payload = {"generated_at": datetime.now(UTC).isoformat(), "status": "CALENDAR_READY" if markets and all(x["status"] == "CALENDAR_READY" for x in markets) else "CALENDAR_BLOCKED", "markets": markets}
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    for name, content in (("CALENDAR_READY.json", text), ("CALENDAR_READY.md", "# CALENDAR_READY\n\n```json\n" + text + "```\n")):
        tmp = out / f".{name}.tmp"; tmp.write_text(content, encoding="utf-8"); tmp.replace(out / name)
    return payload
