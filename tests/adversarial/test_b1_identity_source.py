"""B1 — source/identity and provenance attacks (ADVERSARIAL-E2E-VALIDATION-V1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from adversarial._helpers import (
    AS_OF,
    month_rows,
    workbench_run,
)
from cross_asset.decision_support.binding import (
    FactorBindingRegistry,
    load_factor_bindings,
)
from cross_asset.decision_support.monitoring_adapter import build_monitoring_pack_from_db
from cross_asset.decision_support.producer import (
    score_monitoring_factors,
)
from cross_asset.reports.monitoring_health import monitoring_data_health
from cross_asset.storage._time import utc_naive


def _registry(bindings):
    return FactorBindingRegistry(
        version=1, contract="ADVERSARIAL", bindings=bindings
    )


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _series_file(*series_ids):
    return {
        "series": [
            {"series_id": sid, "frequency": "daily", "unit": "test"}
            for sid in series_ids
        ]
    }


def _sources_file(entries):
    return {"mappings": entries}


# --- B1-01: correct canonical + correct provider/source id -------------------


def test_adv_b1_01_governed_identity_is_accepted_without_formal_authority(
    governed_store
):
    store = governed_store()
    try:
        run_id = "monitoring-fred-adv-b1-01"
        store.start_run("MONITORING:fred", run_id, requested_series=1)
        rows = month_rows(
            "US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)]
        )
        store.insert_observations(rows, run_id=run_id)
        store.finish_run(run_id, "success", success_series=1, failed_series=0)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b1-01"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        assert payroll.provenance["identity_verified"] is True
        assert payroll.provenance["source_refs"] == ["fred:PAYEMS"]
        assert payroll.provenance["formal_admission_granted"] is False
        assert payroll.provenance["formal_readiness"] == "FORMAL_BLOCKED"
    finally:
        store.close()


# --- B1-02: wrong source_series_id -------------------------------------------


def test_adv_b1_02_wrong_source_series_id_is_not_comparable_evidence(governed_store):
    store = governed_store()
    try:
        run_id = "monitoring-fred-adv-b1-02"
        store.start_run("MONITORING:fred", run_id, requested_series=2)
        rows = month_rows(
            "US_CORE_CPI", "PAYEMS", [200 + i for i in range(48)]
        ) + month_rows(
            "US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)]
        )
        store.insert_observations(rows, run_id=run_id)
        store.finish_run(run_id, "success", success_series=2, failed_series=0)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b1-02"))
        cpi = next(item for item in bundle.series if item.series_id == "US_CORE_CPI")
        assert cpi.status == "BLOCKED"
        assert cpi.observations == []
        assert cpi.provenance["identity_verified"] is False
        assert (
            "monitoring_source_series_id_mismatch:PAYEMS"
            in cpi.provenance["identity_blockers"]
        )
        # Raw provenance stays visible for diagnosis; it is never consumed.
        assert cpi.provenance["source_refs"] == ["fred:PAYEMS"]
        assert cpi.provenance["identity_blocked_rows"] == 48

        scores, statuses = score_monitoring_factors(bundle, registry=load_factor_bindings())
        assert scores["US_CORE_CPI_TREND"].missing is True
        assert statuses["US_CORE_CPI_TREND"]["missing"] is True
    finally:
        store.close()


# --- B1-03: provider mismatch ------------------------------------------------


def test_adv_b1_03_row_source_must_match_the_monitoring_run_provider(governed_store):
    store = governed_store()
    try:
        run_id = "monitoring-fred-adv-b1-03"
        store.start_run("MONITORING:fred", run_id, requested_series=1)
        rows = month_rows(
            "US_NONFARM_PAYROLLS",
            "PAYEMS",
            [145000 + i * 145 for i in range(48)],
            source="wind",
        )
        store.insert_observations(rows, run_id=run_id)
        store.finish_run(run_id, "success", success_series=1, failed_series=0)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b1-03"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        assert payroll.status == "BLOCKED"
        assert payroll.observations == []
        assert "monitoring_source_mismatch:wind" in payroll.provenance["identity_blockers"]
    finally:
        store.close()


# --- B1-04..08: config-level binding governance ------------------------------


def test_adv_b1_04_duplicate_canonical_identity_in_binding_is_rejected(tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "US_EQ",
                    "provider": "test",
                    "source_series_id": "SRC_US_EQ",
                    "priority": 1,
                    "enabled": True,
                    "semantic_equivalence": True,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "US_EQ_TREND_63D",
                    "canonical_series_ids": ["US_EQ", "US_EQ"],
                    "transform": {"type": "TREND_63D"},
                    "monitoring": {"route": "R", "status": "BOUND"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="duplicate canonical series"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


def test_adv_b1_05_semantically_non_equivalent_proxy_cannot_be_bound(tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "US_EQ",
                    "provider": "test",
                    "source_series_id": "PROXY",
                    "priority": 1,
                    "enabled": True,
                    "semantic_equivalence": False,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "US_EQ_TREND_63D",
                    "canonical_series_ids": ["US_EQ"],
                    "transform": {"type": "TREND_63D"},
                    "monitoring": {"route": "R", "status": "BOUND"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="semantically equivalent source mapping"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


def test_adv_b1_06_disabled_source_mapping_cannot_be_bound(tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "US_EQ",
                    "provider": "test",
                    "source_series_id": "SRC",
                    "priority": 1,
                    "enabled": False,
                    "semantic_equivalence": True,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "US_EQ_TREND_63D",
                    "canonical_series_ids": ["US_EQ"],
                    "transform": {"type": "TREND_63D"},
                    "monitoring": {"route": "R", "status": "BOUND"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="semantically equivalent source mapping"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


def test_adv_b1_07_ungoverned_canonical_series_is_rejected(tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "INVENTED",
                    "provider": "test",
                    "source_series_id": "SRC",
                    "priority": 1,
                    "enabled": True,
                    "semantic_equivalence": True,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "US_EQ_TREND_63D",
                    "canonical_series_ids": ["INVENTED"],
                    "transform": {"type": "TREND_63D"},
                    "monitoring": {"route": "R", "status": "BOUND"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="ungoverned canonical series"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


def test_adv_b1_08_bound_binding_requires_transform(governed_store, tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "US_EQ",
                    "provider": "test",
                    "source_series_id": "SRC",
                    "priority": 1,
                    "enabled": True,
                    "semantic_equivalence": True,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "US_EQ_TREND_63D",
                    "canonical_series_ids": ["US_EQ"],
                    "monitoring": {"route": "R", "status": "BOUND"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="missing transform"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


# --- B1-09: dual-lane identity (monitoring + formal acceptance) --------------


def test_adv_b1_09_formal_acceptance_does_not_leak_into_monitoring_pack(
    governed_store
):
    from cross_asset.storage import latest_formal_observations_asof

    store = governed_store()
    try:
        run_id = "monitoring-fred-adv-b1-09"
        store.start_run("MONITORING:fred", run_id, requested_series=1)
        rows = month_rows("US_CORE_CPI", "CPILFESL", [200 + i for i in range(48)])
        store.insert_observations(rows, run_id=run_id)
        store.finish_run(run_id, "success", success_series=1, failed_series=0)

        # The read model compares naive UTC timestamps, so normalise explicitly.
        captured = utc_naive(datetime(2026, 9, 12, 0, tzinfo=UTC))
        store.conn.execute(
            """INSERT INTO data_acceptance_registry
               (series_id,provider,source_series_id,status,tech_gate,legal_gate,
                pit_gate,stability_gate,pit_grade,origin,evidence_json,updated_at,
                usage_status)
               VALUES ('US_CORE_CPI','fred','CPILFESL','ACCEPTED','PASS','PASS',
                       'PASS','PASS','A','adversarial-test','{}',?,'LIVE_VERIFIED')""",
            [captured],
        )

        health = monitoring_data_health(
            store.conn,
            as_of=captured,
            market_data_cutoff=AS_OF,
            series_ids=["US_CORE_CPI"],
        )[0]
        assert health["usage_separation"] == "MONITORING_NOT_FORMAL"
        assert health["formal_readiness"] == "FORMAL_BLOCKED"
        assert health["formal_observation_available"] is False

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b1-09"))
        cpi = next(item for item in bundle.series if item.series_id == "US_CORE_CPI")
        assert cpi.provenance["formal_admission_granted"] is False

        formal = latest_formal_observations_asof(
            store.conn,
            captured,
            required_usage_status="LIVE_VERIFIED",
            series_ids=["US_CORE_CPI"],
        )
        # The registry row exists but no monitoring observation carries an
        # approved formal provenance identity, so the formal query stays empty.
        assert formal.empty
    finally:
        store.close()


# --- B1-10: provider error must not silently fall back -----------------------


def test_adv_b1_10_provider_error_never_triggers_silent_source_fallback(
    governed_store
):
    from cross_asset.domain.models import DataRequest
    from cross_asset.ingestion.monitoring import MonitoringRunner

    store = governed_store(("US_GOV_10Y",))

    class FailingProvider:
        name = "fred"

        def fetch(self, request):
            raise RuntimeError("synthetic provider failure")

    result = MonitoringRunner(store, FailingProvider()).run(
        DataRequest(series_ids=["US_GOV_10Y"])
    )
    try:
        assert result["status"] == "failed"
        assert result["rows_written"] == 0
        assert result["formal_admission_attempted"] is False
        attempts = store.conn.execute(
            "SELECT status,fallback,source_switch FROM provider_attempts"
        ).fetchall()
        assert attempts, "failure must be recorded as operational evidence"
        assert all(status == "FAILED" for status, _, _ in attempts)
        assert all(fallback is False for _, fallback, _ in attempts)
        assert all(switch is False for _, _, switch in attempts)
        observations = store.conn.execute("SELECT count(*) FROM observations").fetchone()
        assert observations[0] == 0
    finally:
        store.close()


# --- B1-11: non-monitoring provider rows are excluded ------------------------


def test_adv_b1_11_formal_provider_rows_are_not_monitoring_evidence(governed_store):
    store = governed_store()
    try:
        run_id = "formal-fred-run"
        store.start_run("fred", run_id, requested_series=1)
        rows = month_rows("US_NONFARM_PAYROLLS", "PAYEMS", [145000 + i * 145 for i in range(48)])
        store.insert_observations(rows, run_id=run_id)
        store.finish_run(run_id, "success", success_series=1, failed_series=0)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b1-11"))
        payroll = next(
            item for item in bundle.series if item.series_id == "US_NONFARM_PAYROLLS"
        )
        assert payroll.observations == []
        assert payroll.status in {"MISSING", "BLOCKED"}
        assert payroll.provenance["source_refs"] == []
    finally:
        store.close()


# --- B1-12: Wind-only identity -------------------------------------------------


def test_adv_b1_12_wind_only_identity_is_not_exercisable_in_this_window():
    """NO-WIND window: Wind/manual proprietary identity is NOT_EXERCISED.

    This is a classification test, not a behaviour claim: it asserts that the
    repository keeps Wind disabled and that no Wind evidence is present here.
    """

    with open("config/sources.yml", encoding="utf-8") as handle:
        sources = yaml.safe_load(handle)
    providers = sources["providers"]
    assert providers["wind"]["enabled"] is False
    assert providers["ifind"]["enabled"] is False
    assert providers["tushare"]["enabled"] is False


# --- B1-13: bound binding referencing an unknown factor_id ---------------------


def test_adv_b1_13_binding_referencing_unknown_factor_is_rejected(tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "US_EQ",
                    "provider": "test",
                    "source_series_id": "SRC",
                    "priority": 1,
                    "enabled": True,
                    "semantic_equivalence": True,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "NOT_IN_TAXONOMY",
                    "canonical_series_ids": ["US_EQ"],
                    "transform": {"type": "TREND_63D"},
                    "monitoring": {"route": "R", "status": "BOUND"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="unknown factor_id"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


# --- B1-14: invalid lane status token ------------------------------------------


def test_adv_b1_14_invalid_lane_status_is_rejected(tmp_path):
    series_path = _write(tmp_path, "series.yml", _series_file("US_EQ"))
    sources_path = _write(
        tmp_path,
        "sources.yml",
        _sources_file(
            [
                {
                    "series_id": "US_EQ",
                    "provider": "test",
                    "source_series_id": "SRC",
                    "priority": 1,
                    "enabled": True,
                    "semantic_equivalence": True,
                }
            ]
        ),
    )
    bindings_path = _write(
        tmp_path,
        "bindings.yml",
        {
            "version": 1,
            "contract": "ADVERSARIAL",
            "bindings": [
                {
                    "factor_id": "US_EQ_TREND_63D",
                    "canonical_series_ids": ["US_EQ"],
                    "transform": {"type": "TREND_63D"},
                    "monitoring": {"route": "R", "status": "PARTIAL"},
                    "formal": {"route": "F", "status": "BLOCKED"},
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="invalid monitoring status"):
        load_factor_bindings(
            bindings_path, series_path=series_path, sources_path=sources_path
        )


# --- B1-15: series with no enabled mapping at all ------------------------------


def test_adv_b1_15_series_without_enabled_mapping_blocks_the_run(governed_store):
    # The catalog is seeded for a different provider, so no enabled fred
    # mapping exists for this canonical series.
    store = governed_store(("US_CORE_CPI",), provider="tushare")
    try:
        run_id = "monitoring-fred-adv-b1-15"
        store.start_run("MONITORING:fred", run_id, requested_series=1)
        rows = month_rows("US_CORE_CPI", "CPILFESL", [200 + i for i in range(48)])
        store.insert_observations(rows, run_id=run_id)
        store.finish_run(run_id, "success", success_series=1, failed_series=0)

        bundle = build_monitoring_pack_from_db(store, workbench_run("wb-adv-b1-15"))
        cpi = next(item for item in bundle.series if item.series_id == "US_CORE_CPI")
        assert cpi.status == "BLOCKED"
        assert cpi.observations == []
        assert "monitoring_source_mapping_missing" in cpi.provenance["identity_blockers"]
    finally:
        store.close()
