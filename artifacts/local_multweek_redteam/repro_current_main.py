"""Current-main (036b58450226) reproduction of the three #138 headline findings.

Scratch script: deterministic, offline, no Wind, no network. Synthetic rows are
TEST-ONLY mechanics inputs and are never described as real market evidence.
Run from repo root: python artifacts/local_multweek_redteam/repro_current_main.py
"""
from __future__ import annotations

import pathlib
import tempfile
from datetime import UTC, date, datetime

import pandas as pd

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import build_monitoring_snapshot
from cross_asset.decision_support.serving import SnapshotReadService, SnapshotStore
from cross_asset.operations.workbench_run import WorkbenchRun
from cross_asset.storage.catalog import sync_series_catalog
from cross_asset.storage.duckdb import DuckDBStore

AS_OF = date(2026, 9, 11)
DECISION = datetime(2026, 9, 12, 6, tzinfo=UTC)
CAPTURE = datetime(2026, 9, 12, 0, tzinfo=UTC)


def month_rows(series_id, source_series_id, values, *, capture_time, source="fred", end=date(2026, 9, 1)):
    months = pd.date_range(end=end, periods=len(values), freq="MS")
    return [
        {"series_id": series_id, "observation_date": s.date(), "available_at": capture_time,
         "value": float(v), "source": source, "source_series_id": source_series_id,
         "ingested_at": capture_time, "quality": "ok"}
        for s, v in zip(months, values, strict=True)
    ]


def write_run(store, rows, run_id="monitoring-fred-adv"):
    store.start_run("MONITORING:fred", run_id, requested_series=2)
    store.insert_observations(rows, run_id=run_id)
    store.finish_run(run_id, "success", success_series=2, failed_series=0)


def workbench_run(run_id, *, decision_time, data_cutoff):
    return WorkbenchRun(run_id=run_id, run_kind="shadow", source_mode="LIVE", status="SUCCESS",
                        model_version="workbench_v0.1",
                        config_identity="decision-support-v2:adversarial-test-only",
                        data_cutoff=data_cutoff.isoformat(), decision_time=decision_time.isoformat())


def cpi_path(months, value0=270.0):
    cpi = [value0]
    rates = [0.0018, 0.0022, 0.0027, 0.0031, 0.0025, 0.0020]
    for index in range(1, months):
        cpi.append(cpi[-1] * (1.0 + rates[index % 6]))
    return cpi


print("== ATTACK 1: monitoring read-model identity (#138 ADV-P2-01) ==")
store = DuckDBStore(":memory:")
sync_series_catalog(store, series_ids=["US_CORE_CPI"], provider="fred")
write_run(store, month_rows("US_CORE_CPI", "PAYEMS", cpi_path(40), capture_time=CAPTURE),
          run_id="monitoring-fred-adv-1")
pack = build_monitoring_pack_from_db(store, workbench_run("wb-adv-1", decision_time=DECISION, data_cutoff=AS_OF))
cpi = [s for s in pack.series if s.series_id == "US_CORE_CPI"][0]
print(f"  wrong source_series_id -> status={cpi.status} source_refs={cpi.provenance.get('source_refs')} "
      f"n_obs={len(cpi.observations)} identity_verified={cpi.provenance.get('identity_verified')}")

store2 = DuckDBStore(":memory:")
sync_series_catalog(store2, series_ids=["US_CORE_CPI"], provider="fred")
write_run(store2, month_rows("US_CORE_CPI", "CPIAUCSL", cpi_path(40), capture_time=CAPTURE, source="wind"),
          run_id="monitoring-fred-adv-2")
pack2 = build_monitoring_pack_from_db(store2, workbench_run("wb-adv-2", decision_time=DECISION, data_cutoff=AS_OF))
cpi2 = [s for s in pack2.series if s.series_id == "US_CORE_CPI"][0]
print(f"  row source != run provider -> status={cpi2.status} source_refs={cpi2.provenance.get('source_refs')} "
      f"n_obs={len(cpi2.observations)} identity_verified={cpi2.provenance.get('identity_verified')}")

print("== ATTACK 2: P1-02 latest-pointer monotonicity vs merged #135 ==")


def real_pack(store, *, end_month: date, capture: datetime, decision: datetime, cutoff: date, run_id: str):
    months = 49 if end_month.month == 9 else 48
    payroll = [145000 + i * 145 + (i % 5) * 18 + (i // 12) * 23 for i in range(months)]
    rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", payroll, capture_time=capture, end=end_month)
    rows += month_rows("US_CORE_CPI", "CPILFESL", cpi_path(months), capture_time=capture, end=end_month)
    write_run(store, rows, run_id=run_id)
    return build_monitoring_pack_from_db(store, workbench_run(run_id, decision_time=decision, data_cutoff=cutoff))


store3 = DuckDBStore(":memory:")
sync_series_catalog(store3, series_ids=["US_NONFARM_PAYROLLS", "US_CORE_CPI"], provider="fred")
pack_w1 = real_pack(store3, end_month=date(2026, 8, 1), capture=datetime(2026, 9, 5, tzinfo=UTC),
                    decision=datetime(2026, 9, 5, 6, tzinfo=UTC), cutoff=date(2026, 9, 4),
                    run_id="monitoring-fred-w1")
snap_w1 = build_monitoring_snapshot(pack_w1)
pack_w2 = real_pack(store3, end_month=date(2026, 9, 1), capture=CAPTURE, decision=DECISION, cutoff=AS_OF,
                    run_id="monitoring-fred-w2")
snap_w2 = build_monitoring_snapshot(pack_w2)
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp) / "snapshots"
    store_s = SnapshotStore(root)
    store_s.persist(snap_w2)      # later economic week persists first
    store_s.persist(snap_w1)      # older week, technically written later
    latest = store_s.load_latest()
    verdict = "CLOSED" if latest.metadata.as_of == AS_OF else "STILL_REPRODUCIBLE"
    print(f"  latest after backfill: as_of={latest.metadata.as_of} (expect {AS_OF}) -> {verdict}")
    store_s.persist(snap_w2)      # same-week retry after latest
    latest2 = store_s.load_latest()
    print(f"  latest after same-week retry: as_of={latest2.metadata.as_of} -> "
          f"{'OK' if latest2.metadata.as_of == AS_OF else 'REGRESSED'}")
    (root / "latest.json").write_text("{ not json", encoding="utf-8")
    try:
        store_s.load_latest()
        print("  corrupted latest.json load_latest(): recovered from canonical list")
    except Exception as exc:
        print(f"  corrupted latest.json load_latest(): {type(exc).__name__}: {str(exc)[:90]}")
    try:
        SnapshotReadService(store_s).health()
        print("  corrupted latest.json health(): no error")
    except Exception as exc:
        print(f"  corrupted latest.json health(): {type(exc).__name__}: {str(exc)[:120]}")

print("== ATTACK 3: P1-01 week-2 information set vs new monthly observation ==")
print(f"  week1 info_set={snap_w1.weekly_change.information_set_delta.status}")
try:
    snap2 = build_monitoring_snapshot(pack_w2, previous_snapshot=snap_w1)
    print(f"  week2 built: info_set={snap2.weekly_change.information_set_delta.status}")
except Exception as exc:
    print(f"  week2 RAISED: {type(exc).__name__}: {str(exc)[:180]}")
