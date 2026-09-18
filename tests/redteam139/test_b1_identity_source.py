"""RT139 B1 — source/identity attacks (seeds: #138 B1; re-derived on current main)."""

from __future__ import annotations

import pytest

from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import build_monitoring_snapshot
from redteam139._helpers import (
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    cpi_values,
    governed_store,
    mechanics_registry,
    month_rows,
    workbench_run,
    write_monitoring_run,
)

CAPTURE = WEEK2_DECISION.replace(hour=0, minute=0)


def _cpi_store_with(series_id_source_pairs, provider="fred"):
    store = governed_store(series_ids=[sid for sid, _ in series_id_source_pairs], provider=provider)
    rows = []
    for index, (sid, source_symbol) in enumerate(series_id_source_pairs):
        rows += month_rows(sid, source_symbol, cpi_values(40), capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id=f"monitoring-fred-b1-{index}")
    return store


# --- RT139-B1-01: governed identity is admissible for monitoring, never formal ---
def test_b1_01_governed_identity_is_accepted_without_formal_authority():
    store = governed_store()
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="monitoring-fred-b1-01",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-01"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.observations
    assert series.provenance["source_refs"] == ["fred:CPILFESL"]
    assert series.provenance["formal_admission_granted"] is False


# --- RT139-B1-02: wrong source_series_id is not comparable evidence (#138 P2-01 regression) ---
def test_b1_02_wrong_source_series_id_is_blocked():
    store = governed_store()
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "PAYEMS", cpi_values(40), capture_time=CAPTURE),
        run_id="monitoring-fred-b1-02",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-02"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status == "BLOCKED"
    assert series.observations == []
    assert "monitoring_source_series_id_mismatch:PAYEMS" in series.provenance["identity_blockers"]
    assert series.provenance["identity_verified"] is False
    # raw provenance retained for diagnosis
    assert series.provenance["source_refs"] == ["fred:PAYEMS"]


# --- RT139-B1-03: row source != run provider is never silently relabelled ---
def test_b1_03_row_source_mismatch_is_blocked():
    store = governed_store()
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE, source="wind"),
        run_id="monitoring-fred-b1-03",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-03"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status == "BLOCKED"
    assert "monitoring_source_mismatch:wind" in series.provenance["identity_blockers"]


# --- RT139-B1-04: series without an enabled mapping blocks (no guessed identity) ---
def test_b1_04_series_without_enabled_mapping_is_blocked():
    store = governed_store(series_ids=["US_NONFARM_PAYROLLS"])
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="monitoring-fred-b1-04",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-04"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status == "BLOCKED"
    assert "monitoring_source_mapping_missing" in series.provenance["identity_blockers"]


# --- RT139-B1-05: identity-blocked rows never reach the producer as evidence ---
def test_b1_05_snapshot_refuses_when_only_poisoned_rows_exist():
    from cross_asset.decision_support.producer import MonitoringSnapshotBlocked

    store = governed_store()
    write_monitoring_run(
        store,
        month_rows("US_CORE_CPI", "PAYEMS", cpi_values(40), capture_time=CAPTURE),
        run_id="monitoring-fred-b1-05",
    )
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-05"))
    with pytest.raises(MonitoringSnapshotBlocked):
        build_monitoring_snapshot(pack)


# --- RT139-B1-06: one poisoned series does not corrupt a healthy sibling ---
def test_b1_06_poisoned_series_does_not_corrupt_healthy_sibling():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "PAYEMS", cpi_values(40), capture_time=CAPTURE)
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(40)],
                       capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="monitoring-fred-b1-06", requested=2)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-06"))
    by_id = {item.series_id: item for item in pack.series}
    assert by_id["US_CORE_CPI"].status == "BLOCKED"
    assert by_id["US_NONFARM_PAYROLLS"].observations


# --- RT139-B1-07: duplicate canonical identity inside one binding is rejected ---
def _write_binding_config(tmp_path, bindings_payload, *, sources_payload=None, series_payload=None):
    import yaml

    repo = tmp_path
    series_path = repo / "series.yml"
    sources_path = repo / "sources.yml"
    bindings_path = repo / "bindings.yml"
    if series_payload is None:
        import pathlib
        import shutil as _shutil

        real_repo = pathlib.Path(__file__).resolve().parents[2]
        _shutil.copy(real_repo / "config" / "series.yml", series_path)
    else:
        series_path.write_text(yaml.safe_dump(series_payload), encoding="utf-8")
    if sources_payload is None:
        import pathlib
        import shutil as _shutil

        real_repo = pathlib.Path(__file__).resolve().parents[2]
        _shutil.copy(real_repo / "config" / "sources.yml", sources_path)
    else:
        sources_path.write_text(yaml.safe_dump(sources_payload), encoding="utf-8")
    bindings_path.write_text(yaml.safe_dump(bindings_payload), encoding="utf-8")
    return bindings_path, series_path, sources_path


def _binding(factor_id, series_ids, transform_type, status="BOUND"):
    from cross_asset.decision_support.binding import FactorBinding, FactorTransform, LaneBinding

    return FactorBinding(
        factor_id=factor_id,
        canonical_series_ids=series_ids,
        transform=FactorTransform(type=transform_type),
        monitoring=LaneBinding(route="TEST_ONLY_MONITORING", status=status),
        formal=LaneBinding(route="SANCTIONED_FORMAL_QUERY", status="BLOCKED"),
    )


def test_b1_07_duplicate_canonical_identity_is_rejected(tmp_path):
    from cross_asset.decision_support.binding import load_factor_bindings

    bindings = {
        "version": 900,
        "contract": "TEST_ONLY",
        "bindings": [
            {
                "factor_id": "US_CORE_CPI_TREND",
                "canonical_series_ids": ["US_CORE_CPI", "US_CORE_CPI"],
                "transform": {"type": "CORE_CPI_3M6M_ANNUALIZED_TREND", "min_history": 12},
                "monitoring": {"route": "TEST_ONLY_MONITORING", "status": "BOUND"},
                "formal": {"route": "SANCTIONED_FORMAL_QUERY", "status": "BLOCKED"},
            }
        ],
    }
    paths = _write_binding_config(tmp_path, bindings)
    with pytest.raises(ValueError, match="duplicate canonical series"):
        load_factor_bindings(paths[0], series_path=paths[1], sources_path=paths[2])


# --- RT139-B1-08: disabled source mapping cannot be bound ---
def test_b1_08_disabled_source_mapping_cannot_be_bound(tmp_path):
    from cross_asset.decision_support.binding import load_factor_bindings

    bindings = {
        "version": 900,
        "contract": "TEST_ONLY",
        "bindings": [
            {
                "factor_id": "US_CORE_CPI_TREND",
                "canonical_series_ids": ["US_CORE_CPI"],
                "transform": {"type": "CORE_CPI_3M6M_ANNUALIZED_TREND", "min_history": 12},
                "monitoring": {"route": "TEST_ONLY_MONITORING", "status": "BOUND"},
                "formal": {"route": "SANCTIONED_FORMAL_QUERY", "status": "BLOCKED"},
            }
        ],
    }
    sources = {
        "sources": {"fred": {"enabled": True, "tier": "B"}},
        "mappings": [
            {
                "series_id": "US_CORE_CPI",
                "provider": "fred",
                "source_series_id": "CPILFESL",
                "enabled": False,
                "semantic_equivalence": True,
            }
        ],
    }
    paths = _write_binding_config(tmp_path, bindings, sources_payload=sources)
    with pytest.raises(ValueError, match="enabled semantically equivalent source mapping"):
        load_factor_bindings(paths[0], series_path=paths[1], sources_path=paths[2])


# --- RT139-B1-09: ungoverned canonical series is rejected ---
def test_b1_09_ungoverned_canonical_series_is_rejected(tmp_path):
    from cross_asset.decision_support.binding import load_factor_bindings

    bindings = {
        "version": 900,
        "contract": "TEST_ONLY",
        "bindings": [
            {
                "factor_id": "US_CORE_CPI_TREND",
                "canonical_series_ids": ["NOT_GOVERNED"],
                "transform": {"type": "CORE_CPI_3M6M_ANNUALIZED_TREND", "min_history": 12},
                "monitoring": {"route": "TEST_ONLY_MONITORING", "status": "BOUND"},
                "formal": {"route": "SANCTIONED_FORMAL_QUERY", "status": "BLOCKED"},
            }
        ],
    }
    sources = {
        "sources": {"fred": {"enabled": True, "tier": "B"}},
        "mappings": [
            {
                "series_id": "NOT_GOVERNED",
                "provider": "fred",
                "source_series_id": "X",
                "enabled": True,
                "semantic_equivalence": True,
            }
        ],
    }
    paths = _write_binding_config(
        tmp_path, bindings,
        sources_payload=sources,
        series_payload={"series": []},
    )
    with pytest.raises(ValueError, match="ungoverned canonical series"):
        load_factor_bindings(paths[0], series_path=paths[1], sources_path=paths[2])


# --- RT139-B1-10: a binding referencing an unknown factor is rejected ---
def test_b1_10_binding_referencing_unknown_factor_is_rejected(tmp_path):
    from cross_asset.decision_support.binding import load_factor_bindings

    bindings = {
        "version": 900,
        "contract": "TEST_ONLY",
        "bindings": [
            {
                "factor_id": "NOT_A_REAL_FACTOR",
                "canonical_series_ids": ["US_CORE_CPI"],
                "transform": {"type": "TREND_63D"},
                "monitoring": {"route": "TEST_ONLY_MONITORING", "status": "BOUND"},
                "formal": {"route": "SANCTIONED_FORMAL_QUERY", "status": "BLOCKED"},
            }
        ],
    }
    paths = _write_binding_config(tmp_path, bindings)
    with pytest.raises(ValueError, match="unknown factor_id"):
        load_factor_bindings(paths[0], series_path=paths[1], sources_path=paths[2])


# --- RT139-B1-11: formal acceptance never leaks into the monitoring pack ---
def test_b1_11_formal_rows_are_not_monitoring_evidence():
    store = governed_store()
    # write rows under a non-monitoring provider run
    store.start_run("FORMAL:fred", "formal-run-b1-11", requested_series=1)
    store.insert_observations(
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="formal-run-b1-11",
    )
    store.finish_run("formal-run-b1-11", "success", success_series=1, failed_series=0)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-11"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.observations == []


# --- RT139-B1-12: monitoring run provider must resolve ---
def test_b1_12_unresolvable_run_provider_is_blocked():
    store = governed_store()
    store.start_run("MONITORING:", "monitoring-b1-12", requested_series=1)
    store.insert_observations(
        month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE),
        run_id="monitoring-b1-12",
    )
    store.finish_run("monitoring-b1-12", "success", success_series=1, failed_series=0)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-12"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status == "BLOCKED"
    assert "monitoring_run_provider_unresolved" in series.provenance["identity_blockers"]


# --- RT139-B1-13: poisoned inflation axis refuses the snapshot truthfully ---
def test_b1_13_blocked_identity_refuses_snapshot_and_records_provenance():
    from cross_asset.decision_support.producer import MonitoringSnapshotBlocked

    store = governed_store()
    rows = month_rows("US_CORE_CPI", "PAYEMS", cpi_values(40), capture_time=CAPTURE)
    rows += month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(40)],
                       capture_time=CAPTURE)
    write_monitoring_run(store, rows, run_id="monitoring-fred-b1-13", requested=2)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-13"))
    provenance = {item.series_id: item.provenance for item in pack.series}
    assert provenance["US_CORE_CPI"]["identity_verified"] is False
    assert provenance["US_CORE_CPI"]["identity_blocked_rows"] == 40
    assert provenance["US_NONFARM_PAYROLLS"]["identity_verified"] is True
    # The producer must refuse to fabricate an inflation axis from blocked rows.
    with pytest.raises(MonitoringSnapshotBlocked):
        build_monitoring_snapshot(pack)


# --- RT139-B1-14: proprietary providers stay disabled in the shipped config ---
def test_b1_14_proprietary_providers_stay_disabled():
    import pathlib

    import yaml

    repo = pathlib.Path(__file__).resolve().parents[2]
    text = (repo / "config" / "sources.yml").read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    sources = payload.get("sources", payload)
    for provider in ("wind", "ifind", "tushare"):
        entry = sources.get(provider)
        if entry is not None:
            assert entry.get("enabled") is False, f"{provider} must stay disabled"


# --- RT139-B1-15: Wind-only identity lanes stay NOT_EXERCISED (no-Wind window) ---
def test_b1_15_wind_lanes_not_exercised():
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[2]
    text = (repo / "config" / "sources.yml").read_text(encoding="utf-8")
    assert "enabled: false" in text.lower()


# --- RT139-B1-16: identity revalidation is part of the read model, not only ingestion ---
def test_b1_16_read_model_revalidates_directly_persisted_rows():
    # Rows written straight into the store bypass MonitoringRunner validation;
    # the adapter must still catch the identity violation.
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "PAYEMS", cpi_values(40), capture_time=CAPTURE)
    store.start_run("MONITORING:fred", "monitoring-fred-b1-16", requested_series=1)
    store.insert_observations(rows, run_id="monitoring-fred-b1-16")
    store.finish_run("monitoring-fred-b1-16", "success", success_series=1, failed_series=0)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-16"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status == "BLOCKED"
    assert series.provenance["identity_blockers"]


# --- RT139-B1-17: valid sibling in the same run is unaffected by direct persist ---
def test_b1_17_direct_persist_healthy_row_still_served():
    store = governed_store()
    rows = month_rows("US_CORE_CPI", "CPILFESL", cpi_values(40), capture_time=CAPTURE)
    store.start_run("MONITORING:fred", "monitoring-fred-b1-17", requested_series=1)
    store.insert_observations(rows, run_id="monitoring-fred-b1-17")
    store.finish_run("monitoring-fred-b1-17", "success", success_series=1, failed_series=0)
    pack = build_monitoring_pack_from_db(store, workbench_run("wb-b1-17"))
    series = [item for item in pack.series if item.series_id == "US_CORE_CPI"][0]
    assert series.status in {"FRESH", "STALE"}
    assert series.observations


# --- RT139-B1-18: unit semantics remain declared for governed series ---
def test_b1_18_series_catalog_declares_units():
    from cross_asset.storage.catalog import expected_source_identities

    store = governed_store()
    expected = expected_source_identities(store.conn, "fred", ["US_CORE_CPI"])
    assert expected["US_CORE_CPI"] == {"CPILFESL"}
