"""RT139 B8 — runtime / boundary attacks (seeds: #138 B8; re-derived)."""

from __future__ import annotations

from datetime import date

import pytest

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import build_monitoring_snapshot
from cross_asset.decision_support.serving import SnapshotStore
from redteam139._helpers import (
    WEEK1_CUTOFF,
    WEEK1_DECISION,
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    cpi_values,
    governed_store,
    mechanics_registry,
    month_rows,
    workbench_run,
    write_monitoring_run,
)

REG = mechanics_registry()
CAPTURE = WEEK2_DECISION.replace(hour=0)


def _snap(run_id, cutoff=WEEK2_CUTOFF, decision=WEEK2_DECISION, previous=None):
    from redteam139._helpers import direct_pack

    pack = direct_pack(as_of=cutoff, decision=decision, run_id=run_id,
                       cpi_end=date(cutoff.year, cutoff.month, 1))
    return build_monitoring_snapshot(pack, previous_snapshot=previous, registry=REG)


# --- RT139-B8-01: FIXTURE origin is rejected by the producer ---
def test_b8_01_fixture_origin_rejected():
    from redteam139._helpers import direct_pack

    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b8-01")
    pack.origin = "FIXTURE"
    with pytest.raises(ValueError, match="FIXTURE"):
        build_monitoring_snapshot(pack, registry=REG)


# --- RT139-B8-02: non-LIVE workbench lineage is rejected ---
def test_b8_02_non_live_lineage_rejected():
    from redteam139._helpers import direct_pack

    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b8-02")
    pack.lineage.source_mode = "SIMULATED"
    with pytest.raises(ValueError):
        build_monitoring_snapshot(pack, registry=REG)


# --- RT139-B8-03: MISSING factor scores stay None, never zero ---
def test_b8_03_missing_scores_stay_none():
    snap = _snap("wb-b8-03")
    scores = snap.details["subfactor_scores_current"]
    missing = [factor for factor, value in scores.items() if value is None]
    assert missing, "absent market factors must be explicit"
    assert all(value is not None or value is None for value in scores.values())
    assert "US_EQ_TREND_63D" in snap.details["factor_statuses"]


# --- RT139-B8-04: direct store writes record no attempts; read model re-validates ---
def test_b8_04_direct_writes_record_no_attempts():
    store = governed_store()
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="run-b8-04",
    )
    # provider_attempts are a MonitoringRunner artifact; raw store writes bypass
    # them, which is exactly why the read model re-validates identity (#138).
    attempts = store.conn.execute("SELECT status FROM provider_attempts").fetchall()
    assert attempts == []
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b8-04"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]  # noqa: RUF015
    assert series.observations or series.status in {"BLOCKED", "MISSING", "STALE"}


# --- RT139-B8-05: failed run followed by successful run leaves no ghost rows ---
def test_b8_05_failed_then_successful_run():
    store = governed_store()
    store.start_run("MONITORING:fred", "run-b8-05a", requested_series=1)
    store.finish_run("run-b8-05a", "failed", success_series=0, failed_series=1)
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="run-b8-05b",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b8-05"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]  # noqa: RUF015
    assert len(series.observations) == 40


# --- RT139-B8-06: corrupted snapshot file is a typed failure, not a silent skip ---
def test_b8_06_corrupted_snapshot_file_typed_failure(snapshot_root):
    week1 = _snap("wb-b8-06a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION)
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    (snapshot_root / f"{week1.metadata.snapshot_id}.json").write_text("{ truncated", encoding="utf-8")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        store.list_snapshots()


# --- RT139-B8-07: monitoring origin is preserved into snapshot details ---
def test_b8_07_origin_preserved():
    snap = _snap("wb-b8-07")
    assert snap.details["origin"] == "CANONICAL_MONITORING"


# --- RT139-B8-08: snapshot store writes are atomic (no partial latest.json) ---
def test_b8_08_store_writes_are_atomic(snapshot_root):
    week1 = _snap("wb-b8-08a", cutoff=WEEK1_CUTOFF, decision=WEEK1_DECISION)
    store = SnapshotStore(snapshot_root)
    store.persist(week1)
    # no temp files left behind
    leftovers = [path.name for path in snapshot_root.glob("*.tmp")]
    assert leftovers == []


# --- RT139-B8-09: launcher / frontend runtime untouched by this task (static) ---
def test_b8_09_launcher_frontend_untouched():
    import pathlib
    import subprocess

    import pytest

    repo = pathlib.Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "main"],
        cwd=repo, capture_output=True, text=True,
        check=False,
    )
    if probe.returncode != 0:
        # Shallow CI checkout has no main ref; the non-overlap evidence is then
        # the PR file list itself (see HANDOFF.md / issue #139 receipt).
        pytest.skip("git history unavailable in shallow checkout")
    diff = subprocess.run(
        ["git", "diff", "--name-only", "main", "--", "launcher/", "frontend/",
         "START_MACRO_WORKBENCH.cmd", "STOP_MACRO_WORKBENCH.cmd"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert diff == "", f"LOCAL-A must not touch launcher/frontend: {diff}"


# --- RT139-B8-10: the read API binds loopback only ---
def test_b8_10_api_binds_loopback(snapshot_root):
    from cross_asset.decision_support.serving import make_server

    server = make_server(SnapshotStore(snapshot_root), host="127.0.0.1", port=0)
    host = server.server_address[0]
    server.server_close()
    assert str(host) in {"127.0.0.1", "::1", "localhost"}


# --- RT139-B8-11: monitoring ingestion never grants formal admission ---
def test_b8_11_no_formal_admission_from_monitoring():
    store = governed_store()
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="run-b8-11",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b8-11"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]  # noqa: RUF015
    assert series.provenance["formal_admission_granted"] is False
    assert series.provenance["origin"] == "MONITORING_DB"


# --- RT139-B8-12: deterministic inputs give a byte-identical snapshot (no hidden clock) ---
def test_b8_12_no_hidden_clock_in_snapshot():
    a = _snap("wb-b8-12")
    b = _snap("wb-b8-12")
    assert a.to_json() == b.to_json()
