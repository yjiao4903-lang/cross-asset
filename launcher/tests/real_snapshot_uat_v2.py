from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cross_asset.decision_support.binding import load_factor_bindings
from cross_asset.decision_support.decision_history import snapshot_economic_week_id
from cross_asset.decision_support.serving import SnapshotStore
from cross_asset.domain.models import DataRequest
from cross_asset.ingestion.monitoring import MonitoringRunner
from cross_asset.operations.workbench_run import WorkbenchRun, persist_run
from cross_asset.providers.monitoring import FREDMonitoringProvider, YahooMonitoringProvider
from cross_asset.storage.duckdb import DuckDBStore

EXPECTED_IDENTITIES = {
    "US_NONFARM_PAYROLLS": {"provider": "fred", "source_series_id": "PAYEMS", "unit": "thousands_persons"},
    "US_CORE_CPI": {"provider": "fred", "source_series_id": "CPILFESL", "unit": "index_1982_1984_100"},
    "US_REAL_10Y": {"provider": "fred", "source_series_id": "DFII10", "unit": "yield_percent"},
    "US_EQ": {"provider": "yahoo", "source_series_id": "^GSPC", "unit": "index_points"},
}
PROVIDER_REQUESTS = {
    "fred": ["US_NONFARM_PAYROLLS", "US_CORE_CPI", "US_REAL_10Y"],
    "yahoo": ["US_EQ"],
}


def _now() -> datetime:
    return datetime.now(UTC)


def _safe(value: object, limit: int = 400) -> str:
    return str(value or "")[:limit]


def _rows(conn, sql: str, params=()) -> list[dict]:
    cursor = conn.execute(sql, params)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _markdown(payload: dict) -> str:
    lines = [
        "# Real Snapshot UAT V2",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: **{payload['status']}**",
        "",
        "## Runtime roots",
        "",
        f"- DB: `{payload['paths']['db']}`",
        f"- Workbench: `{payload['paths']['runs_root']}`",
        f"- Snapshots: `{payload['paths']['snapshot_root']}`",
        "",
        "## Provider ingestion",
        "",
    ]
    for name, result in payload["providers"].items():
        lines += [
            f"### {name.upper()}",
            "",
            f"- status: `{result.get('status')}`",
            f"- rows_written: `{result.get('rows_written', 0)}`",
            f"- formal_admission_attempted: `{result.get('formal_admission_attempted')}`",
            f"- errors: `{json.dumps(result.get('errors') or {}, ensure_ascii=False)}`",
            "",
        ]
    lines += [
        "## Identity / provenance",
        "",
        f"- real observation rows: `{payload['real_observation_rows']}`",
        f"- acceptance registry rows: `{payload['acceptance_registry_rows']}`",
        f"- all real ingestion lineage MONITORING: `{payload['all_ingestion_lineage_monitoring']}`",
        f"- exact identity checks passed: `{payload['identity_checks_passed']}`",
        "",
    ]
    snapshot = payload.get("snapshot")
    if snapshot:
        lines += [
            "## Persisted snapshot",
            "",
            f"- snapshot_id: `{snapshot['snapshot_id']}`",
            f"- run_id: `{snapshot['run_id']}`",
            f"- economic_week_id: `{snapshot['economic_week_id']}`",
            f"- lane: `{snapshot['lane']}`",
            f"- history technical count: `{snapshot['technical_history_count']}`",
            f"- history canonical count: `{snapshot['canonical_history_count']}`",
            f"- data health: `{snapshot['data_health_overall']}`",
            f"- missing components: `{', '.join(snapshot['missing_components'])}`",
            f"- stale components: `{', '.join(snapshot['stale_components'])}`",
            f"- blockers: `{', '.join(snapshot['blockers'])}`",
            f"- all snapshot provenance formal_admission_granted=false: `{snapshot['all_provenance_nonformal']}`",
            "",
        ]
    if payload["blockers"]:
        lines += ["## Blockers", ""] + [f"- {item}" for item in payload["blockers"]] + [""]
    return "\n".join(lines) + "\n"


def _identity_evidence(store: DuckDBStore, ingestion_run_ids: list[str]) -> tuple[list[dict], list[dict]]:
    if not ingestion_run_ids:
        return [], []
    placeholders = ",".join("?" for _ in ingestion_run_ids)
    observations = _rows(
        store.conn,
        f"""SELECT series_id,source,source_series_id,count(*) AS row_count,
                   min(observation_date) AS first_observation_date,
                   max(observation_date) AS last_observation_date,
                   min(available_at) AS first_available_at,
                   max(available_at) AS last_available_at,
                   min(run_id) AS run_id
            FROM observations
            WHERE run_id IN ({placeholders})
            GROUP BY series_id,source,source_series_id
            ORDER BY series_id,source,source_series_id""",
        ingestion_run_ids,
    )
    catalog = _rows(
        store.conn,
        """SELECT c.series_id,c.frequency,c.unit,c.currency,m.provider,m.source_series_id,
                  m.enabled,m.semantic_equivalence
           FROM series_catalog c
           JOIN source_mapping m ON m.series_id=c.series_id
           WHERE c.series_id IN ('US_NONFARM_PAYROLLS','US_CORE_CPI','US_REAL_10Y','US_EQ')
           ORDER BY c.series_id,m.provider,m.source_series_id""",
    )
    for row in observations:
        for key in ("first_observation_date", "last_observation_date", "first_available_at", "last_available_at"):
            if row.get(key) is not None:
                row[key] = str(row[key])
    return observations, catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Real public-provider -> persisted snapshot UAT for #140")
    parser.add_argument("--artifact-root", default="artifacts/windows_uat_v2")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    artifact_root = (repo_root / args.artifact_root).resolve() if not Path(args.artifact_root).is_absolute() else Path(args.artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    db_path = artifact_root / f"monitoring-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.duckdb"
    runs_root = artifact_root / "workbench"
    snapshot_root = artifact_root / "dashboard_snapshots"
    runs_root.mkdir(parents=True, exist_ok=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)

    generated = _now()
    token = generated.strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {
        "contract": "WINDOWS-REAL-SNAPSHOT-SOAK-UAT-V2",
        "generated_at": generated.isoformat(),
        "status": "IN_PROGRESS",
        "paths": {
            "db": str(db_path),
            "runs_root": str(runs_root),
            "snapshot_root": str(snapshot_root),
        },
        "providers": {},
        "blockers": [],
    }

    store = DuckDBStore(db_path)
    store_open = True
    ingestion_run_ids: list[str] = []
    try:
        start = date.today() - timedelta(days=2500)
        end = date.today()
        providers = {
            "fred": FREDMonitoringProvider(timeout=args.timeout),
            "yahoo": YahooMonitoringProvider(timeout=args.timeout),
        }
        for name, provider in providers.items():
            run_id = f"monitoring-{name}-windows-uat-v2-{token}"
            result = MonitoringRunner(store, provider).run(
                DataRequest(series_ids=PROVIDER_REQUESTS[name], start=start, end=end),
                run_id=run_id,
            )
            payload["providers"][name] = result
            ingestion_run_ids.append(run_id)
            if int(result.get("rows_written") or 0) <= 0:
                payload["blockers"].append(
                    f"provider:{name}:no_real_rows:{_safe(result.get('errors'))}"
                )

        observations, catalog = _identity_evidence(store, ingestion_run_ids)
        payload["observation_identities"] = observations
        payload["catalog_identities"] = catalog
        payload["real_observation_rows"] = sum(int(row["row_count"]) for row in observations)
        payload["acceptance_registry_rows"] = store.conn.execute(
            "SELECT count(*) FROM data_acceptance_registry"
        ).fetchone()[0]
        ingestion_rows = _rows(
            store.conn,
            "SELECT run_id,provider,status,rows_written,error_summary FROM ingestion_runs WHERE run_id IN ("
            + ",".join("?" for _ in ingestion_run_ids)
            + ") ORDER BY run_id",
            ingestion_run_ids,
        )
        payload["ingestion_runs"] = ingestion_rows
        payload["all_ingestion_lineage_monitoring"] = bool(ingestion_rows) and all(
            str(row.get("provider") or "").startswith("MONITORING:") for row in ingestion_rows
        )

        checks = []
        observed_by_series = {row["series_id"]: row for row in observations}
        catalog_by_series = {
            (row["series_id"], str(row["provider"]).lower(), row["source_series_id"]): row
            for row in catalog
        }
        for series_id, expected in EXPECTED_IDENTITIES.items():
            provider_result = payload["providers"][expected["provider"]]
            if int(provider_result.get("rows_written") or 0) <= 0:
                checks.append({"series_id": series_id, "status": "NOT_EXERCISED_PROVIDER_BLOCKED"})
                continue
            row = observed_by_series.get(series_id)
            catalog_row = catalog_by_series.get((series_id, expected["provider"], expected["source_series_id"]))
            passed = bool(
                row
                and str(row["source"]).lower() == expected["provider"]
                and row["source_series_id"] == expected["source_series_id"]
                and catalog_row
                and catalog_row["unit"] == expected["unit"]
                and bool(catalog_row["enabled"])
                and bool(catalog_row["semantic_equivalence"])
            )
            checks.append(
                {
                    "series_id": series_id,
                    "status": "PASS" if passed else "FAIL",
                    "expected": expected,
                    "observation": row,
                    "catalog": catalog_row,
                }
            )
            if not passed:
                payload["blockers"].append(f"identity_check_failed:{series_id}")
        payload["identity_checks"] = checks
        payload["identity_checks_passed"] = all(
            item["status"] in {"PASS", "NOT_EXERCISED_PROVIDER_BLOCKED"} for item in checks
        )

        registry = load_factor_bindings()
        bound_series = sorted(
            {
                sid
                for binding in registry.bindings
                if binding.monitoring.status == "BOUND"
                for sid in binding.canonical_series_ids
            }
        )
        available_series = sorted(observed_by_series)
        unavailable_bound = sorted(set(bound_series) - set(available_series))
        payload["bound_series"] = bound_series
        payload["available_real_series"] = available_series
        payload["unavailable_bound_series"] = unavailable_bound
        for series_id in unavailable_bound:
            payload["blockers"].append(f"bound_series_real_source_unavailable:{series_id}")

        if payload["real_observation_rows"] == 0:
            payload["status"] = "REAL_PROVIDER_EXTERNAL_BLOCKER"
            payload["snapshot"] = None
        else:
            decision_time = _now()
            workbench_run = WorkbenchRun(
                run_id=f"wb-live-windows-uat-v2-{token}",
                run_kind="shadow",
                source_mode="LIVE",
                status="PARTIAL" if payload["blockers"] else "SUCCESS",
                model_version="workbench_v0.1",
                config_identity="windows-real-snapshot-soak-uat-v2",
                data_cutoff=str(date.today()),
                decision_time=decision_time.isoformat(),
                components={"monitoring_ingestion_runs": ingestion_run_ids},
                warnings=["REAL_MONITORING_PARTIAL_COVERAGE"] if payload["blockers"] else [],
                blockers=list(payload["blockers"]),
                provenance={
                    "origin": "MONITORING",
                    "formal_gate": False,
                    "ingestion_run_ids": ingestion_run_ids,
                },
                created_at=decision_time.isoformat(),
            )
            persist_run(workbench_run, runs_root)
            payload["workbench_run"] = workbench_run.to_dict()

            # Windows DuckDB holds a single-writer file lock: release the parent
            # connection before the snapshot_cli subprocess opens the same DB.
            store.close()
            store_open = False

            command = [
                sys.executable,
                "-m",
                "cross_asset.decision_support.snapshot_cli",
                "build",
                "--db",
                str(db_path),
                "--run-id",
                workbench_run.run_id,
                "--runs-root",
                str(runs_root),
                "--root",
                str(snapshot_root),
            ]
            proc = subprocess.run(
                command,
                cwd=repo_root,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            payload["snapshot_build_cli"] = {
                "command": [
                    sys.executable,
                    "-m",
                    "cross_asset.decision_support.snapshot_cli",
                    "build",
                    "--db",
                    str(db_path),
                    "--run-id",
                    workbench_run.run_id,
                    "--runs-root",
                    str(runs_root),
                    "--root",
                    str(snapshot_root),
                ],
                "exit_code": proc.returncode,
                "stdout": _safe(proc.stdout, 1200),
                "stderr": _safe(proc.stderr, 1200),
            }
            if proc.returncode != 0:
                payload["blockers"].append(f"snapshot_build_cli_failed:{proc.returncode}")
                payload["status"] = "CODE_PATH_DEFECT"
                payload["snapshot"] = None
            else:
                match = re.search(r"snapshot_id=([^\s]+)", proc.stdout)
                snapshot_store = SnapshotStore(snapshot_root)
                snapshot = snapshot_store.load(match.group(1)) if match else snapshot_store.load_latest()
                technical = snapshot_store.list_snapshots()
                canonical = snapshot_store.list_canonical()
                provenance = dict(snapshot.details.get("series_provenance") or {})
                provenance_rows = [
                    item for item in provenance.values() if isinstance(item, dict)
                ]
                all_nonformal = bool(provenance_rows) and all(
                    item.get("formal_admission_granted") is False
                    for item in provenance_rows
                )
                dh = snapshot.data_health_summary
                payload["snapshot"] = {
                    "snapshot_id": snapshot.metadata.snapshot_id,
                    "run_id": snapshot.metadata.run_id,
                    "economic_week_id": snapshot_economic_week_id(snapshot),
                    "lane": str(getattr(snapshot.metadata.lane, "value", snapshot.metadata.lane)),
                    "as_of": snapshot.metadata.as_of.isoformat(),
                    "decision_time": snapshot.metadata.decision_time.isoformat(),
                    "data_cutoff": str(snapshot.details.get("data_cutoff")),
                    "technical_history_count": len(technical),
                    "canonical_history_count": len(canonical),
                    "data_health_overall": str(getattr(dh.overall, "value", dh.overall)),
                    "missing_components": list(dh.missing_components),
                    "stale_components": list(dh.stale_components),
                    "blockers": list(dh.blockers),
                    "binding_counts": snapshot.details.get("binding_counts", {}),
                    "factor_statuses": snapshot.details.get("factor_statuses", {}),
                    "series_provenance": provenance,
                    "all_provenance_nonformal": all_nonformal,
                }
                payload["status"] = "REAL_SNAPSHOT_PERSISTED"
                if snapshot.metadata.run_id != workbench_run.run_id:
                    payload["blockers"].append("snapshot_workbench_run_mismatch")
                if str(getattr(snapshot.metadata.lane, "value", snapshot.metadata.lane)) != "MONITORING":
                    payload["blockers"].append("snapshot_lane_not_monitoring")
                if payload["acceptance_registry_rows"] != 0 or not all_nonformal:
                    payload["blockers"].append("formal_admission_boundary_violation")
                if payload["blockers"]:
                    payload["status"] = "REAL_SNAPSHOT_PERSISTED_PARTIAL"
    finally:
        if store_open:
            store.close()

    payload["blockers"] = sorted(set(payload["blockers"]))
    (artifact_root / "REAL_SNAPSHOT_UAT.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (artifact_root / "REAL_SNAPSHOT_UAT.md").write_text(
        _markdown(payload), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "real_observation_rows": payload.get("real_observation_rows", 0),
                "snapshot_id": (payload.get("snapshot") or {}).get("snapshot_id"),
                "blockers": payload["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
