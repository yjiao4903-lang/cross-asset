"""Canonical workbench run object for daily/shadow/replay surfaces.

Persists JSON artifacts only. Does not migrate storage schema, change
allocation economics, or admit sources. LIVE previous-valid state is
isolated from FIXTURE/SIMULATED runs.
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
_EXIT_BY_STATUS = {"SUCCESS": 0, "PARTIAL": 0, "DATA_BLOCKED": 2, "FAILED": 1}


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


def state_path(root: str | Path | None = None) -> Path:
    path = default_runs_root(root) / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path / "formal_previous_valid.json"


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


def load_formal_previous_valid(root: str | Path | None = None) -> dict | None:
    path = state_path(root)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("source_mode") != FORMAL_SOURCE_MODE:
        return None
    if payload.get("allocation_status") != "ACTIVE":
        return None
    if payload.get("status") != "SUCCESS":
        return None
    return payload


def record_formal_previous_valid(run: WorkbenchRun, root: str | Path | None = None) -> bool:
    """Persist previous-valid weights only from a successful formal LIVE run."""

    run.validate()
    if run.source_mode != FORMAL_SOURCE_MODE:
        return False
    if run.status != "SUCCESS" or run.allocation_status != "ACTIVE":
        return False
    if not run.weights:
        return False
    payload = {
        "run_id": run.run_id,
        "source_mode": run.source_mode,
        "status": run.status,
        "allocation_status": run.allocation_status,
        "weights": dict(run.weights),
        "recorded_at": datetime.now(UTC).isoformat(),
        "source": "formal",
    }
    state_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return True


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


def persist_and_maybe_record(run: WorkbenchRun, root: str | Path | None = None) -> WorkbenchRun:
    persist_run(run, root)
    record_formal_previous_valid(run, root)
    return run


__all__ = [
    "FORMAL_SOURCE_MODE",
    "SOURCE_MODES",
    "TERMINAL_STATUSES",
    "WorkbenchRun",
    "apply_frozen_from_previous_valid",
    "blocked_run",
    "component_view",
    "from_pipeline_payload",
    "load_formal_previous_valid",
    "load_run",
    "new_run_id",
    "normalize_terminal_status",
    "persist_and_maybe_record",
    "persist_run",
    "record_formal_previous_valid",
]
