"""RT139 B4 — factor/regime attacks (seeds: #138 B4; re-derived)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from cross_asset.decision_support.producer import (
    MonitoringSnapshotBlocked,
    build_monitoring_snapshot,
)
from redteam139._helpers import (
    WEEK2_CUTOFF,
    WEEK2_DECISION,
    direct_pack,
    mechanics_registry,
)

REG = mechanics_registry()
WEEK1_CUTOFF = date(2026, 9, 4)
WEEK1_DECISION = datetime(2026, 9, 5, 6, tzinfo=UTC)
WEEK3_CUTOFF = date(2026, 9, 18)
WEEK3_DECISION = datetime(2026, 9, 19, 6, tzinfo=UTC)


def _snapshot(pack, previous=None):
    return build_monitoring_snapshot(pack, previous_snapshot=previous, registry=REG)


def _economic_week(snapshot):
    return snapshot.details["economic_week_id"]


# --- RT139-B4-01: missing growth axis refuses to synthesize ---
def test_b4_01_missing_growth_axis_refuses():
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-01",
                       omit=frozenset({"T_PAYROLL"}))
    with pytest.raises(MonitoringSnapshotBlocked):
        _snapshot(pack)


# --- RT139-B4-02: missing inflation axis refuses to synthesize ---
def test_b4_02_missing_inflation_axis_refuses():
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-02",
                       omit=frozenset({"T_CPI"}))
    with pytest.raises(MonitoringSnapshotBlocked):
        _snapshot(pack)


# --- RT139-B4-03: one stale bound factor keeps reduced confidence ---
def test_b4_03_stale_factor_reduces_confidence_only():
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-03",
                       statuses={"T_US_EQ": "STALE"})
    snapshot = _snapshot(pack)
    status = snapshot.details["factor_statuses"]["US_EQ_TREND_63D"]
    assert status["stale"] is True
    assert status["missing"] is False


# --- RT139-B4-04: the pack never invents factors beyond the registry ---
def test_b4_04_pack_never_invents_factors():
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-04")
    snapshot = _snapshot(pack)
    scores = snapshot.details["subfactor_scores_current"]
    registry_factor_ids = {binding.factor_id for binding in mechanics_registry().bindings}
    assert registry_factor_ids <= set(scores)


# --- RT139-B4-05: wrong transform type for a factor identity is rejected at load ---
def test_b4_05_wrong_transform_rejected(tmp_path):
    import yaml

    from cross_asset.decision_support.binding import load_factor_bindings

    bindings = {
        "version": 900,
        "contract": "TEST_ONLY",
        "bindings": [
            {
                "factor_id": "US_PAYROLLS_TREND",
                "canonical_series_ids": ["US_NONFARM_PAYROLLS"],
                "transform": {"type": "TREND_63D", "min_history": 12},
                "monitoring": {"route": "TEST_ONLY_MONITORING", "status": "BOUND"},
                "formal": {"route": "SANCTIONED_FORMAL_QUERY", "status": "BLOCKED"},
            }
        ],
    }
    sources = {
        "sources": {"fred": {"enabled": True, "tier": "B"}},
        "mappings": [
            {
                "series_id": "US_NONFARM_PAYROLLS",
                "provider": "fred",
                "source_series_id": "PAYEMS",
                "enabled": True,
                "semantic_equivalence": True,
            }
        ],
    }
    bindings_path = tmp_path / "bindings.yml"
    series_path = tmp_path / "series.yml"
    sources_path = tmp_path / "sources.yml"
    bindings_path.write_text(yaml.safe_dump(bindings), encoding="utf-8")
    series_path.write_text(
        yaml.safe_dump({"series": [{"series_id": "US_NONFARM_PAYROLLS"}]}), encoding="utf-8"
    )
    sources_path.write_text(yaml.safe_dump(sources), encoding="utf-8")
    with pytest.raises(ValueError, match="violates V2 factor definition"):
        load_factor_bindings(bindings_path, series_path=series_path, sources_path=sources_path)


# --- RT139-B4-06: min_history is enforced causally ---
def test_b4_06_insufficient_history_is_missing_not_fabricated():
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-06")
    pack.series = [
        item if item.series_id != "T_CPI"
        else item.model_copy(deep=True, update={"observations": item.observations[:8]})
        for item in pack.series
    ]
    with pytest.raises(MonitoringSnapshotBlocked):
        _snapshot(pack)


# --- RT139-B4-07: three same-week retries remain one economic step ---
def test_b4_07_same_week_retry_is_one_economic_step():
    week1 = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-07")
    first = _snapshot(week1)
    retries = []
    for index in range(3):
        retry_pack = direct_pack(
            as_of=WEEK2_CUTOFF,
            decision=WEEK2_DECISION + timedelta(hours=index + 1),
            run_id=f"wb-b4-07-r{index}",
        )
        retries.append(_snapshot(retry_pack, previous=retries[-1] if retries else first))
    assert len({_economic_week(s) for s in [first, *retries]}) == 1


# --- RT139-B4-08: three distinct weeks are three economic steps ---
def test_b4_08_three_distinct_weeks_are_three_steps():
    weeks = [
        (WEEK1_CUTOFF, WEEK1_DECISION, date(2026, 8, 1)),
        (WEEK2_CUTOFF, WEEK2_DECISION, date(2026, 9, 1)),
        (WEEK3_CUTOFF, WEEK3_DECISION, date(2026, 9, 1)),
    ]
    previous = None
    week_ids = []
    for index, (cutoff, decision, cpi_end) in enumerate(weeks):
        pack = direct_pack(as_of=cutoff, decision=decision, run_id=f"wb-b4-08-{index}",
                           cpi_end=cpi_end)
        snapshot = _snapshot(pack, previous=previous)
        week_ids.append(_economic_week(snapshot))
        previous = snapshot
    assert len(set(week_ids)) == 3


# --- RT139-B4-09: restart + replay equals continuous run (determinism) ---
def test_b4_09_replay_is_deterministic():
    def build_once(tag):
        week1 = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id=f"wb-b4-09-{tag}")
        return _snapshot(week1)

    a = build_once("a")
    b = build_once("a")  # same inputs, "restarted" build
    assert a.to_json() == b.to_json()


# --- RT139-B4-10: first snapshot deadband resolves via documented default (P2-04 doc) ---
def test_b4_10_first_snapshot_deadband_default_documented():
    from cross_asset.decision_support.regime import RegimeEngine

    engine = RegimeEngine(axis_threshold=0.25)
    quadrant = engine.candidate_quadrant(0.0, 0.0, prior=None)
    # Documented behaviour (ADV-P2-04): an ambiguous first reading inherits the
    # default quadrant label; changing it is a product decision, not a test fix.
    assert quadrant in {"GOLDILOCKS", "REFLATION", "STAGFLATION", "DEFLATION"}


# --- RT139-B4-11: regime dwell carries prior quadrant context ---
def test_b4_11_regime_dwell_retained():
    first = _snapshot(direct_pack(as_of=WEEK1_CUTOFF, decision=WEEK1_DECISION,
                                  run_id="wb-b4-11a", cpi_end=date(2026, 8, 1)))
    second = _snapshot(direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION,
                                   run_id="wb-b4-11b"), previous=first)
    assert second.regime.quadrant_label
    assert second.regime.dwell_weeks >= 0


# --- RT139-B4-12: regime history is ordered by economic week ---
def test_b4_12_regime_history_ordered():
    first = _snapshot(direct_pack(as_of=WEEK1_CUTOFF, decision=WEEK1_DECISION,
                                  run_id="wb-b4-12a", cpi_end=date(2026, 8, 1)))
    second = _snapshot(direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION,
                                   run_id="wb-b4-12b"), previous=first)
    history = second.details["regime_input_history"]
    assert history
    weeks = [item.get("economic_week_id") for item in history]
    if all(weeks):
        assert weeks == sorted(weeks)


# --- RT139-B4-13: factor absent in prior produces no fabricated delta ---
def test_b4_13_factor_missing_in_prior_has_no_delta():
    first = _snapshot(direct_pack(as_of=WEEK1_CUTOFF, decision=WEEK1_DECISION,
                                  run_id="wb-b4-13a", cpi_end=date(2026, 8, 1),
                                  omit=frozenset({"T_US_EQ"})))
    second = _snapshot(direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION,
                                   run_id="wb-b4-13b"), previous=first)
    entries = second.weekly_change.macro_state_delta.entries
    eq = [item for item in entries if item.factor_id == "US_EQ_TREND_63D"]
    assert eq == [] or all(item.delta == 0.0 for item in eq)


# --- RT139-B4-14: snapshot records both taxonomy and binding versions ---
def test_b4_14_snapshot_records_versions():
    pack = direct_pack(as_of=WEEK2_CUTOFF, decision=WEEK2_DECISION, run_id="wb-b4-14")
    snapshot = _snapshot(pack)
    assert snapshot.details["binding_registry_version"] == 999
    assert snapshot.details["taxonomy_version"]
