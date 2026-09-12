"""Canonical workbench run object for daily/shadow/replay surfaces.

Persists JSON artifacts only. Does not migrate storage schema, change
allocation economics, or admit sources. Formal previous-valid allocation
is derived only from persisted WorkbenchRun objects that passed the #18
formal query gate. There is no parallel state file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

TERMINAL_STATUSES = ("SUCCESS", "PARTIAL", "DATA_BLOCKED", "FAILED")
SOURCE_MODES = ("LIVE", "FIXTURE", "SIMULATED")
FORMAL_SOURCE_MODE = "LIVE"
FORMAL_QUERY = "latest_formal_observations_asof"
FORMAL_USAGE_STATUS = "LIVE_VERIFIED"
_EXIT_BY_STATUS = {"SUCCESS": 0, "PARTIAL": 0, "DATA_BLOCKED": 2, "FAILED": 1}
_UNHEALTHY_ALLOCATION = {"DATA_BLOCKED", "FAIL", "FAILED", "FROZEN", "DEGRADED"}


@dataclass
class WorkbenchRun:
    run_id: str
    run_kind: str
    source_mode: str
    status: str
    model_version: str
    config_identity: str
    data_cutoff: str | None
    allocation_status: str | None = None
    previous_valid_run_id: str | None = None
    previous_valid_source: str | None = None
    freeze_reason: str | None = None
    components: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    weights: dict | None = None
    created_at: str = ""
    artifact_path: str | None = None

    def validate(self) -> None:
        if self.source_mode not in SOURCE_MODES:
            raise ValueError(f"source_mode_invalid:{self.source_mode}")
        if self.status not in TERMINAL_STATUSES:
            raise ValueError(f"status_invalid:{self.status}")
        if self.source_mode != FORMAL_SOURCE_MODE and self.previous_valid_source == "formal":
            raise ValueError("fixture_or_simulated_cannot_claim_formal_previous_valid")

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)

    @property
    def exit_code(self) -> int:
        return _EXIT_BY_STATUS[self.status]


def new_run_id(prefix: str = "wb") -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def default_runs_root(root: str | Path | None = None) -> Path:
    return Path(root or "artifacts/workbench")


def runs_dir(root: str | Path | None = None) -> Path:
    path = default_runs_root(root) / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def persist_run(run: WorkbenchRun, root: str | Path | None = None) -> WorkbenchRun:
    run.validate()
    if not run.created_at:
        run.created_at = datetime.now(UTC).isoformat()
    path = runs_dir(root) / f"{run.run_id}.json"
    run.artifact_path = str(path)
    path.write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return run


def load_run(run_id: str, root: str | Path | None = None) -> WorkbenchRun:
    path = runs_dir(root) / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"run_not_found:{run_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    run = WorkbenchRun(**payload)
    run.validate()
    return run


def list_runs(root: str | Path | None = None) -> list[WorkbenchRun]:
    """Load every canonical persisted run. Invalid files are skipped."""

    items: list[WorkbenchRun] = []
    directory = runs_dir(root)
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            run = WorkbenchRun(**payload)
            run.validate()
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        items.append(run)
    return items


def is_formal_previous_valid_eligible(run: WorkbenchRun) -> bool:
    """LIVE label is not enough; eligibility requires the #18 formal query gate."""

    run.validate()
    provenance = run.provenance if isinstance(run.provenance, dict) else {}
    return (
        run.source_mode == FORMAL_SOURCE_MODE
        and run.status == "SUCCESS"
        and run.allocation_status == "ACTIVE"
        and bool(run.weights)
        and provenance.get("formal_gate") is True
        and provenance.get("formal_query") == FORMAL_QUERY
        and provenance.get("required_usage_status") == FORMAL_USAGE_STATUS
    )


def load_formal_previous_valid(root: str | Path | None = None) -> dict | None:
    """Latest eligible formal ACTIVE run from persisted WorkbenchRun objects."""

    eligible = [run for run in list_runs(root) if is_formal_previous_valid_eligible(run)]
    if not eligible:
        return None
    eligible.sort(key=lambda run: (run.created_at or "", run.run_id))
    chosen = eligible[-1]
    return {
        "run_id": chosen.run_id,
        "source_mode": chosen.source_mode,
        "status": chosen.status,
        "allocation_status": chosen.allocation_status,
        "weights": dict(chosen.weights or {}),
        "source": "formal",
        "formal_query": (chosen.provenance or {}).get("formal_query"),
        "required_usage_status": (chosen.provenance or {}).get("required_usage_status"),
    }


def record_formal_previous_valid(run: WorkbenchRun, root: str | Path | None = None) -> bool:
    """Keep the run in the canonical lineage. Do not write a parallel state file."""

    persist_run(run, root)
    return is_formal_previous_valid_eligible(run)


def needs_frozen_restore(run: WorkbenchRun) -> bool:
    if run.source_mode != FORMAL_SOURCE_MODE:
        return False
    if run.status in {"DATA_BLOCKED", "FAILED"}:
        return True
    return str(run.allocation_status or "").upper() in _UNHEALTHY_ALLOCATION


def apply_frozen_from_previous_valid(
    run: WorkbenchRun,
    root: str | Path | None = None,
    *,
    reason: str,
) -> WorkbenchRun:
    previous = load_formal_previous_valid(root)
    if previous is None:
        run.status = "DATA_BLOCKED"
        run.allocation_status = "FROZEN"
        run.freeze_reason = reason
        run.blockers = list(run.blockers) + ["previous_valid_formal_allocation_missing"]
        run.weights = None
        return run
    run.allocation_status = "FROZEN"
    run.freeze_reason = reason
    run.previous_valid_run_id = previous["run_id"]
    run.previous_valid_source = "formal"
    run.weights = dict(previous["weights"])
    if run.status == "SUCCESS":
        run.status = "PARTIAL"
    return run


def blocked_run(
    *,
    run_kind: str,
    source_mode: str,
    blockers: list[str],
    status: str = "DATA_BLOCKED",
    model_version: str = "workbench_v0.1",
    config_identity: str = "undeclared",
    data_cutoff: str | None = None,
) -> WorkbenchRun:
    prefix = (run_kind or "wb")[:2]
    return WorkbenchRun(
        run_id=new_run_id(prefix),
        run_kind=run_kind,
        source_mode=source_mode,
        status=status,
        model_version=model_version,
        config_identity=config_identity,
        data_cutoff=data_cutoff,
        blockers=list(blockers),
        components={},
        created_at=datetime.now(UTC).isoformat(),
    )


def component_view(run: WorkbenchRun, name: str) -> dict:
    payload = run.components.get(name) if isinstance(run.components, dict) else None
    if payload in (None, {}, []):
        return {"status": "UNAVAILABLE", "reason": "data_gap", "value": None}
    if isinstance(payload, dict) and payload.get("status") in {None, "", "MISSING"}:
        return {**payload, "status": "UNAVAILABLE", "reason": payload.get("reason") or "data_gap"}
    return payload


def normalize_terminal_status(raw: str | None, *, default: str = "FAILED") -> str:
    text = str(raw or default).upper()
    if text in TERMINAL_STATUSES:
        return text
    if text in {"SIMULATED_SUCCESS", "OK", "READY", "ACTIVE"}:
        return "SUCCESS"
    if text in {"DEGRADED", "PARTIAL_SUCCESS"}:
        return "PARTIAL"
    if text in {"FAIL", "ERROR"}:
        return "FAILED"
    if text in {"BLOCKED", "UNAVAILABLE"}:
        return "DATA_BLOCKED"
    return default


def from_pipeline_payload(
    payload: dict,
    *,
    run_kind: str,
    source_mode: str,
    default_status: str = "PARTIAL",
) -> WorkbenchRun:
    raw_status = payload.get("status")
    status = normalize_terminal_status(raw_status, default=default_status)
    allocation_status = payload.get("allocation_status")
    if allocation_status == "FROZEN" and status == "SUCCESS":
        status = "PARTIAL"
    components = {
        "market": payload.get("market") or payload.get("market_state"),
        "macro": payload.get("macro") or payload.get("macro_state"),
        "style": payload.get("style") or payload.get("style_state"),
        "asset": payload.get("asset_scores") or payload.get("assets"),
        "allocation": payload.get("allocation"),
        "data_health": payload.get("data_health") or payload.get("quality_health"),
    }
    cutoff = payload.get("data_cutoff")
    if isinstance(cutoff, dict):
        cutoff = cutoff.get("cross_market") or cutoff.get("marco") or json.dumps(cutoff, default=str)
    raw_weights = payload.get("weights")
    if not isinstance(raw_weights, dict):
        raw_weights = payload.get("allocation") if isinstance(payload.get("allocation"), dict) else None
    run_id = str(payload.get("run_id") or new_run_id(run_kind[:2] if run_kind else "wb"))
    return WorkbenchRun(
        run_id=run_id,
        run_kind=run_kind,
        source_mode=source_mode,
        status=status,
        model_version=str(payload.get("model_version") or "workbench_v0.1"),
        config_identity=str(payload.get("config_hash") or payload.get("config_identity") or run_kind),
        data_cutoff=str(cutoff) if cutoff else None,
        allocation_status=allocation_status,
        freeze_reason=payload.get("freeze_reason"),
        components={key: value for key, value in components.items() if value not in (None, {}, [])},
        warnings=list(payload.get("warnings") or []),
        blockers=list(payload.get("blockers") or []),
        provenance={"pipeline_status": raw_status, "payload_keys": sorted(payload)},
        weights=raw_weights,
    )


def stamp_formal_gate_from_payload(run: WorkbenchRun, payload: dict) -> WorkbenchRun:
    """Mark #18 formal-query identity when the daily Marco path produced the payload."""

    if str(payload.get("macro_source") or "").strip().lower() != "marco":
        return run
    provenance = dict(run.provenance or {})
    provenance["macro_source"] = "marco"
    provenance["formal_query"] = FORMAL_QUERY
    provenance["required_usage_status"] = FORMAL_USAGE_STATUS
    provenance["formal_gate"] = True
    run.provenance = provenance
    return run


def persist_and_maybe_record(run: WorkbenchRun, root: str | Path | None = None) -> WorkbenchRun:
    """Persist the canonical run only. Eligibility is derived from that lineage."""

    return persist_run(run, root)


def persist_from_cli_payload(
    payload: dict,
    *,
    run_kind: str,
    source_mode: str,
    root: str | Path | None = None,
) -> WorkbenchRun:
    """Persist a pipeline CLI JSON payload as the canonical workbench run."""

    run = from_pipeline_payload(payload, run_kind=run_kind, source_mode=source_mode)
    stamp_formal_gate_from_payload(run, payload)
    if payload.get("status") in {"DATA_BLOCKED", "BLOCKED", "UNAVAILABLE"} and not run.blockers:
        run.blockers = ["pipeline_data_blocked"]
        run.status = "DATA_BLOCKED"
    if needs_frozen_restore(run):
        reason = run.blockers[0] if run.blockers else str(run.allocation_status or run.status)
        apply_frozen_from_previous_valid(run, root, reason=reason)
    return persist_run(run, root)


__all__ = [
    "FORMAL_QUERY",
    "FORMAL_SOURCE_MODE",
    "FORMAL_USAGE_STATUS",
    "SOURCE_MODES",
    "TERMINAL_STATUSES",
    "WorkbenchRun",
    "apply_frozen_from_previous_valid",
    "blocked_run",
    "component_view",
    "from_pipeline_payload",
    "is_formal_previous_valid_eligible",
    "list_runs",
    "load_formal_previous_valid",
    "load_run",
    "needs_frozen_restore",
    "new_run_id",
    "normalize_terminal_status",
    "persist_and_maybe_record",
    "persist_from_cli_payload",
    "persist_run",
    "record_formal_previous_valid",
    "stamp_formal_gate_from_payload",
]
