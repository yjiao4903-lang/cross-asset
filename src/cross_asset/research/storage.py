"""Persistence for frozen research plans and fold-level OOS results."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from cross_asset.storage._time import utc_naive


def _digest(payload) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(body).hexdigest()


def persist_research_plan(
    store,
    *,
    plan: dict,
    config_hash: str,
    code_version: str,
    data_snapshot_id: str | None = None,
) -> dict:
    signature = {
        "protocol_hash": plan["protocol_hash"],
        "plan": plan,
        "config_hash": config_hash,
        "code_version": code_version,
        "data_snapshot_id": data_snapshot_id,
    }
    run_id = f"research-{_digest(signature)[:24]}"
    existing = store.conn.execute(
        "SELECT research_run_id FROM research_runs WHERE research_run_id=?",
        [run_id],
    ).fetchone()
    if existing:
        return {"research_run_id": run_id, "reused": True}

    now = datetime.now(UTC).replace(tzinfo=None)
    store.conn.execute(
        """INSERT INTO research_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            run_id,
            plan["protocol_hash"],
            config_hash,
            code_version,
            plan["status"],
            bool(plan["holdout_sealed"]),
            utc_naive(plan.get("development_start")),
            utc_naive(plan.get("development_end")),
            utc_naive(plan.get("holdout_start")),
            utc_naive(plan.get("holdout_end")),
            int(plan.get("holdout_count", 0)),
            int(plan.get("fold_count", 0)),
            json.dumps(plan.get("blockers", []), sort_keys=True),
            json.dumps(plan, sort_keys=True, default=str),
            now,
        ],
    )
    return {"research_run_id": run_id, "reused": False}


def persist_fold_result(
    store,
    *,
    research_run_id: str,
    fold: int,
    benchmark: str,
    metrics: dict,
    data_snapshot_id: str | None,
    status: str,
) -> None:
    row = store.conn.execute(
        "SELECT holdout_sealed,plan_json FROM research_runs WHERE research_run_id=?",
        [research_run_id],
    ).fetchone()
    if row is None:
        raise KeyError("research_run_not_found")
    plan = json.loads(row[1])
    folds = {int(item["fold"]): item for item in plan.get("folds", [])}
    manifest = folds.get(int(fold))
    if manifest is None:
        raise ValueError("fold_not_in_frozen_plan")
    now = datetime.now(UTC).replace(tzinfo=None)
    metrics_json = json.dumps(metrics, sort_keys=True, default=str)
    existing_result = store.conn.execute(
        """SELECT observation_count,metrics_json,data_snapshot_id,status
           FROM research_fold_results
           WHERE research_run_id=? AND fold=? AND phase=? AND benchmark=?""",
        [research_run_id, int(fold), "WALK_FORWARD", benchmark],
    ).fetchone()
    if existing_result is not None:
        expected = (int(metrics.get("observations", 0)), metrics_json, data_snapshot_id, status)
        if tuple(existing_result) == expected:
            return
        raise ValueError("research_fold_result_conflict")
    store.conn.execute(
        """INSERT INTO research_fold_results
           (research_run_id,fold,phase,benchmark,train_start,train_end,test_start,test_end,
            observation_count,metrics_json,data_snapshot_id,status,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(research_run_id,fold,phase,benchmark) DO UPDATE SET
             observation_count=excluded.observation_count,
             metrics_json=excluded.metrics_json,
             data_snapshot_id=excluded.data_snapshot_id,
             status=excluded.status,
             created_at=excluded.created_at""",
        [
            research_run_id,
            int(fold),
            "WALK_FORWARD",
            benchmark,
            utc_naive(manifest["train_start"]),
            utc_naive(manifest["train_end"]),
            utc_naive(manifest["test_start"]),
            utc_naive(manifest["test_end"]),
            int(metrics.get("observations", 0)),
            metrics_json,
            data_snapshot_id,
            status,
            now,
        ],
    )


__all__ = ["persist_fold_result", "persist_research_plan"]
