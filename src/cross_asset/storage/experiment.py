"""Persistence and trace queries for LOCAL_EXPERIMENT runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from .provenance import ProvenanceStore


def _digest(payload) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def persist_local_experiment(
    store,
    *,
    result: dict,
    snapshot_rows: list[dict],
    decision_time,
    config_hash: str,
    code_version: str,
) -> dict:
    """Persist one deterministic local experiment; identical inputs reuse the run."""
    provenance = ProvenanceStore(store.conn)
    snapshot_id = provenance.create_snapshot(
        snapshot_rows, data_cutoff=decision_time, config_hash_value=config_hash
    )
    signature = {
        "run_mode": "LOCAL_EXPERIMENT",
        "decision_time": str(decision_time),
        "snapshot_id": snapshot_id,
        "config_hash": config_hash,
        "code_version": code_version,
        "model_version": "local_experiment_v0.1",
    }
    key = _digest(signature)
    existing = store.conn.execute(
        "SELECT run_id FROM model_runs WHERE idempotency_key=?", [key]
    ).fetchone()
    if existing:
        return {"run_id": existing[0], "snapshot_id": snapshot_id, "idempotency_key": key, "reused": True}

    run_id = f"localexp-{key[:24]}"
    requested = ["CN_EQ", "HK_EQ", "US_EQ", "CN_BOND", "GOLD", "COMMODITY", "CASH"]
    available = list(result["scope"])
    excluded = list(result["excluded_assets"])
    now = datetime.now(UTC).replace(tzinfo=None)
    with store.atomic():
        provenance.start_model_run(
            "local_experiment",
            decision_time,
            "local_experiment_v0.1",
            config_hash,
            code_version,
            snapshot_id,
            decision_time,
            result.get("warnings", []),
            run_id,
        )
        store.conn.execute(
            """UPDATE model_runs SET run_mode=?,universe_status=?,requested_assets=?,
               available_assets=?,excluded_assets=?,idempotency_key=? WHERE run_id=?""",
            [
                "LOCAL_EXPERIMENT",
                "PARTIAL",
                json.dumps(requested),
                json.dumps(available),
                json.dumps(excluded),
                key,
                run_id,
            ],
        )
        factors = []
        for series_id, state in result["market"]["assets"].items():
            for name, raw_value in state.get("trend", {}).items():
                factors.append(("market_trend", name, series_id, raw_value, raw_value, 1.0, 1.0, raw_value is not None, None, "market_v0.1"))
        for name, state in result["macro"]["dimensions"].items():
            factors.append(("macro", name, "MACRO", state.get("score"), state.get("score"), state.get("confidence"), state.get("coverage"), state.get("score") is not None, None, "macro_v0.1"))
        size = result["style"].get("SIZE", {})
        factors.append(("style", "SIZE", "CN_EQ", size.get("score"), size.get("score"), size.get("confidence"), 1.0 if size.get("status") == "AVAILABLE" else 0.0, size.get("status") == "AVAILABLE", None if size.get("status") == "AVAILABLE" else size.get("status"), "style_v0.1"))
        store.conn.executemany(
            """INSERT INTO factor_values VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (run_id, decision_time, family, name, entity, raw, score, confidence, coverage, available_flag, reason, model, decision_time, now)
                for family, name, entity, raw, score, confidence, coverage, available_flag, reason, model in factors
            ],
        )
        for asset_id, score in result["asset_scores"].items():
            components = score.get("contributions", {})
            coverage = sum(value is not None for value in components.values()) / len(components)
            store.conn.execute(
                """INSERT INTO asset_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    run_id, decision_time, asset_id, components.get("macro"), components.get("trend"),
                    components.get("valuation"), components.get("carry"), components.get("risk"),
                    components.get("structure"), score.get("score"), score.get("confidence"),
                    score.get("model_version", "asset_score_v0.1"), decision_time, coverage,
                    "[]", now,
                ],
            )
        allocation = result["allocation"]
        freeze_reason = ";".join(allocation.get("warnings", [])) or None
        for asset_id, final_weight in allocation["weights"].items():
            attr = allocation["attribution"][asset_id]
            store.conn.execute(
                """INSERT INTO allocation_results VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [run_id, decision_time, asset_id, attr["strategic_weight"], attr["raw_tilt"], attr["constraint_adjusted_tilt"], final_weight, allocation["status"], freeze_reason, now],
            )
        provenance.finish_model_run(run_id, "success", result.get("warnings", []))
    return {"run_id": run_id, "snapshot_id": snapshot_id, "idempotency_key": key, "reused": False}


def explain_run(connection, run_id: str) -> dict:
    run = connection.execute("SELECT * FROM model_runs WHERE run_id=?", [run_id]).fetchone()
    if not run:
        raise KeyError("run_not_found")
    run_columns = [row[0] for row in connection.execute("DESCRIBE model_runs").fetchall()]
    run_record = dict(zip(run_columns, run))
    snapshot = connection.execute("SELECT * FROM data_snapshots WHERE snapshot_id=?", [run_record["data_snapshot_id"]]).fetchone()
    snapshot_columns = [row[0] for row in connection.execute("DESCRIBE data_snapshots").fetchall()]
    snapshot_record = dict(zip(snapshot_columns, snapshot)) if snapshot else None
    factors = connection.execute("SELECT * FROM factor_values WHERE run_id=? ORDER BY factor_family,factor_name,entity_id", [run_id]).fetchdf().to_dict("records")
    scores = connection.execute("SELECT * FROM asset_scores WHERE run_id=? ORDER BY asset_id", [run_id]).fetchdf().to_dict("records")
    allocations = connection.execute("SELECT * FROM allocation_results WHERE run_id=? ORDER BY asset_id", [run_id]).fetchdf().to_dict("records")
    manifest = json.loads(snapshot_record["manifest_json"]) if snapshot_record else []
    raw_hashes = sorted({row.get("raw_hash") for row in manifest if row.get("raw_hash")})
    source_series = sorted({row.get("source_series_id") for row in manifest if row.get("source_series_id")})
    if snapshot_record:
        # Keep the canonical manifest in DuckDB while making the CLI audit view
        # bounded; a full Wind snapshot can otherwise produce several MB.
        snapshot_record.pop("manifest_json", None)
        snapshot_record["manifest_entry_count"] = len(manifest)
    return {"run": run_record, "snapshot": snapshot_record, "raw_hashes": raw_hashes, "source_series_ids": source_series, "factors": factors, "asset_scores": scores, "allocation_results": allocations}


__all__ = ["explain_run", "persist_local_experiment"]
