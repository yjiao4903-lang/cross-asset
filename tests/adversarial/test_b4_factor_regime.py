"""B4 — factor binding / regime / transform attacks (ADVERSARIAL-E2E-VALIDATION-V1)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from adversarial._helpers import (
    AS_OF,
    BLOCKED_LANE,
    DECISION,
    MONITORING_LANE,
    mechanics_registry,
    pack,
)
from cross_asset.decision_support.binding import (
    FactorBinding,
    FactorBindingRegistry,
    FactorTransform,
    load_factor_bindings,
)
from cross_asset.decision_support.enums import HorizonClass, QuadrantLabel
from cross_asset.decision_support.horizon import (
    HorizonMixingError,
    SubfactorScore,
    aggregate_cluster_horizon,
    aggregate_context,
    aggregate_horizon,
)
from cross_asset.decision_support.producer import (
    build_monitoring_snapshot,
    score_monitoring_factors,
)
from cross_asset.decision_support.regime import (
    RegimeEngine,
    RegimeInsufficientDataError,
    evaluate_lens_disagreement,
)
from cross_asset.decision_support.taxonomy import load_taxonomy, signed_score

# --- B4-01/02: missing regime axes ---------------------------------------------


def test_adv_b4_01_missing_growth_axis_blocks_the_snapshot_instead_of_defaulting():
    from cross_asset.decision_support.producer import MonitoringSnapshotBlocked

    with pytest.raises(MonitoringSnapshotBlocked, match="regime axes unavailable"):
        build_monitoring_snapshot(
            pack(omit=frozenset({"T_PAYROLL"})), registry=mechanics_registry()
        )


def test_adv_b4_02_missing_inflation_axis_blocks_the_snapshot_instead_of_defaulting():
    from cross_asset.decision_support.producer import MonitoringSnapshotBlocked

    with pytest.raises(MonitoringSnapshotBlocked, match="regime axes unavailable"):
        build_monitoring_snapshot(
            pack(omit=frozenset({"T_CPI"})), registry=mechanics_registry()
        )


# --- B4-03/04: stale and unbound factors ---------------------------------------


def test_adv_b4_03_one_bound_factor_stale_keeps_reduced_confidence_only():
    bundle = pack(statuses={"T_PAYROLL": "STALE"})
    scores, _statuses = score_monitoring_factors(bundle, registry=mechanics_registry())
    assert scores["US_PAYROLLS_TREND"].stale is True
    assert scores["US_PAYROLLS_TREND"].confidence == 0.5
    assert scores["US_CORE_CPI_TREND"].confidence == 1.0


def test_adv_b4_04_unbound_factor_remains_explicitly_missing():
    bundle = pack()
    scores, statuses = score_monitoring_factors(bundle)
    assert scores["US_ISM_PMI"].missing is True
    assert scores["US_ISM_PMI"].score is None
    assert statuses["US_ISM_PMI"]["monitoring"] == "UNBOUND"


# --- B4-05/06: wrong transform / sign inversion --------------------------------


def test_adv_b4_05_wrong_transform_for_factor_identity_is_rejected(tmp_path):
    import yaml

    (tmp_path / "series.yml").write_text(
        yaml.safe_dump({"series": [{"series_id": "US_EQ", "frequency": "daily", "unit": "x"}]}),
        encoding="utf-8",
    )
    (tmp_path / "sources.yml").write_text(
        yaml.safe_dump(
            {
                "mappings": [
                    {
                        "series_id": "US_EQ",
                        "provider": "test",
                        "source_series_id": "SRC",
                        "priority": 1,
                        "enabled": True,
                        "semantic_equivalence": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bad = tmp_path / "bindings.yml"
    bad.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "contract": "ADVERSARIAL",
                "bindings": [
                    {
                        "factor_id": "US_PAYROLLS_TREND",
                        "canonical_series_ids": ["US_EQ"],
                        "transform": {"type": "TREND_63D"},
                        "monitoring": {"route": "R", "status": "BOUND"},
                        "formal": {"route": "F", "status": "BLOCKED"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="violates V2 factor definition"):
        load_factor_bindings(
            bad, series_path=tmp_path / "series.yml", sources_path=tmp_path / "sources.yml"
        )


def test_adv_b4_06_sign_is_applied_exactly_once_at_the_taxonomy_boundary():
    taxonomy = load_taxonomy()
    negative = [s for s in taxonomy.subfactors() if s.sign == -1]
    assert negative, "the taxonomy must contain negative-sign lenses"
    for spec in negative:
        assert signed_score(spec, 1.0) == -1.0
        assert signed_score(spec, -2.0) == 2.0
    positive = next(s for s in taxonomy.subfactors() if s.sign == 1)
    assert signed_score(positive, 1.5) == 1.5


# --- B4-07/08: same-week retry vs distinct weeks --------------------------------


def test_adv_b4_07_same_economic_week_retry_never_creates_a_new_regime_week():
    registry = mechanics_registry()
    previous = build_monitoring_snapshot(pack(), registry=registry)
    for index in range(3):
        current = pack(
            decision=DECISION + timedelta(hours=index + 1), run_id=f"wb-adv-retry-{index}"
        )
        snapshot = build_monitoring_snapshot(
            current, previous_snapshot=previous, registry=registry
        )
        previous = snapshot
    history = previous.details["regime_input_history"]
    assert [item["economic_week_id"] for item in history] == ["2026-09-07"]
    assert previous.regime.dwell_weeks == 1


def test_adv_b4_08_three_distinct_economic_weeks_accumulate_dwell():
    registry = mechanics_registry()
    previous = build_monitoring_snapshot(pack(), registry=registry)
    for offset in (7, 14):
        current = pack(
            as_of=AS_OF + timedelta(days=offset),
            decision=DECISION + timedelta(days=offset),
            run_id=f"wb-adv-week-{offset}",
        )
        previous = build_monitoring_snapshot(
            current, previous_snapshot=previous, registry=registry
        )
    history = previous.details["regime_input_history"]
    assert [item["economic_week_id"] for item in history] == [
        "2026-09-07",
        "2026-09-14",
        "2026-09-21",
    ]
    assert previous.regime.dwell_weeks == 3


# --- B4-09: restart + replay is deterministic -----------------------------------


def test_adv_b4_09_restart_replay_matches_continuous_process():
    registry = mechanics_registry()
    first = build_monitoring_snapshot(pack(), registry=registry)
    second_input = pack(
        as_of=AS_OF + timedelta(days=7),
        decision=DECISION + timedelta(days=7),
        run_id="wb-adv-replay-2",
    )
    continuous = build_monitoring_snapshot(
        second_input, previous_snapshot=first, registry=registry
    )
    replayed = build_monitoring_snapshot(
        second_input, previous_snapshot=first, registry=registry
    )
    assert continuous.to_json() == replayed.to_json()


# --- B4-10: late-created backfill cannot masquerade as a later economic week ----


def test_adv_b4_10_backfilled_older_week_cannot_displace_the_economic_latest():
    registry = mechanics_registry()
    latest = build_monitoring_snapshot(
        pack(
            as_of=AS_OF + timedelta(days=14),
            decision=DECISION + timedelta(days=14),
            run_id="wb-adv-latest",
        ),
        registry=registry,
    )
    earlier = pack(run_id="wb-adv-backfill")
    with pytest.raises(ValueError, match="must_precede_current_decision_time"):
        build_monitoring_snapshot(earlier, previous_snapshot=latest, registry=registry)


# --- B4-11: future prior --------------------------------------------------------


def test_adv_b4_11_future_prior_is_rejected():
    registry = mechanics_registry()
    prior = build_monitoring_snapshot(
        pack(
            as_of=AS_OF + timedelta(days=7),
            decision=DECISION + timedelta(days=7),
            run_id="wb-adv-prior",
        ),
        registry=registry,
    )
    current = pack(run_id="wb-adv-current")
    with pytest.raises(ValueError, match="must_precede_current_decision_time"):
        build_monitoring_snapshot(current, previous_snapshot=prior, registry=registry)


# --- B4-12/13: deadband and exact thresholds ------------------------------------


@pytest.mark.parametrize(
    "growth,inflation,expected",
    [
        (0.25, -0.25, QuadrantLabel.GOLDILOCKS),
        (-0.25, 0.25, QuadrantLabel.GOLDILOCKS),
        (0.2500001, -0.2500001, QuadrantLabel.GOLDILOCKS),
        (0.2500001, 0.2500001, QuadrantLabel.REFLATION),
        (-0.2500001, 0.2500001, QuadrantLabel.STAGFLATION_RISK),
        (-0.2500001, -0.2500001, QuadrantLabel.DISINFLATIONARY_SLUMP),
    ],
)
def test_adv_b4_12_regime_deadband_and_exact_threshold_behaviour(growth, inflation, expected):
    engine = RegimeEngine(axis_threshold=0.25)
    assert engine.candidate_quadrant(growth, inflation) is expected


def test_adv_b4_13_axis_state_stickiness_inside_the_deadband():
    engine = RegimeEngine(axis_threshold=0.25)
    prior = engine.update(
        growth_score=0.5,
        growth_direction="RISING",
        inflation_score=-0.5,
        inflation_direction="FALLING",
        inflation_state="LOW",
    )
    inside = engine.update(
        growth_score=0.0,
        growth_direction="FLAT",
        inflation_score=0.0,
        inflation_direction="FLAT",
        inflation_state="MODERATE",
        prior=prior,
    )
    # Inside the deadband the prior axis state is retained, never re-guessed.
    assert inside.growth_state.value == prior.growth_state.value
    assert inside.resolved_quadrant() is prior.resolved_quadrant()


# --- B4-14: missing axis is never zero-filled -----------------------------------


def test_adv_b4_14_regime_engine_refuses_a_missing_axis():
    engine = RegimeEngine()
    with pytest.raises(RegimeInsufficientDataError, match="MISSING != ZERO"):
        engine.update(
            growth_score=None,
            growth_direction="FLAT",
            inflation_score=0.1,
            inflation_direction="FLAT",
            inflation_state="MODERATE",
        )


# --- B4-15: partial coverage / lens disagreement --------------------------------


def test_adv_b4_15_partial_coverage_is_reported_not_smoothed_away():
    scores = [
        SubfactorScore(factor_id="A", horizon=HorizonClass.CYCLICAL, score=1.0),
        SubfactorScore(
            factor_id="B", horizon=HorizonClass.CYCLICAL, score=None, missing=True
        ),
    ]
    aggregate = aggregate_cluster_horizon(scores, horizon=HorizonClass.CYCLICAL)
    assert aggregate.score == 1.0
    assert aggregate.coverage == 0.5
    assert aggregate.missing == ["B"]


def test_adv_b4_16_lens_disagreement_requires_two_lenses():
    assert evaluate_lens_disagreement({"only": 1.0}).flag is False
    flagged = evaluate_lens_disagreement({"a": 1.5, "b": 0.0}, threshold=1.0)
    assert flagged.flag is True


# --- B4-17: horizon mixing and structural-context isolation --------------------


def test_adv_b4_17_horizon_mixing_is_rejected():
    with pytest.raises(HorizonMixingError):
        aggregate_cluster_horizon(
            [
                SubfactorScore(factor_id="A", horizon=HorizonClass.CYCLICAL, score=1.0),
                SubfactorScore(factor_id="B", horizon=HorizonClass.TACTICAL, score=1.0),
            ],
            horizon=HorizonClass.CYCLICAL,
        )
    with pytest.raises(HorizonMixingError):
        aggregate_context(
            [SubfactorScore(factor_id="A", horizon=HorizonClass.CYCLICAL, score=1.0)]
        )


def test_adv_b4_18_structural_context_never_enters_a_macro_aggregate():
    with pytest.raises(HorizonMixingError, match="STRUCTURAL_CONTEXT"):
        aggregate_horizon(
            [
                SubfactorScore(
                    factor_id="V", horizon=HorizonClass.STRUCTURAL_CONTEXT, score=1.0
                )
            ],
            horizon=HorizonClass.CYCLICAL,
        )


# --- B4-19: wrong arity for a spread transform ---------------------------------


def test_adv_b4_19_spread_transform_requires_exactly_two_series():
    registry = FactorBindingRegistry(
        version=1,
        contract="ADVERSARIAL",
        bindings=[
            FactorBinding(
                factor_id="US_YIELD_CURVE_10Y2Y",
                canonical_series_ids=["T_CPI"],
                transform=FactorTransform(type="SPREAD_CAUSAL_ZSCORE", min_history=12),
                monitoring=MONITORING_LANE,
                formal=BLOCKED_LANE,
            )
        ],
    )
    with pytest.raises(ValueError, match="needs two series"):
        score_monitoring_factors(pack(), registry=registry)


# --- B4-20: first snapshot with ambiguous axes ---------------------------------


def test_adv_b4_20_first_snapshot_all_deadband_resolves_via_the_documented_default():
    """LEDGER ADV-P2-04: with no prior, an all-deadband reading resolves to the
    documented default quadrant (GOLDILOCKS) rather than an explicit unknown.
    Recorded as a diagnosability gap; behaviour is deterministic and documented.
    """

    engine = RegimeEngine(axis_threshold=0.25)
    quadrant = engine.candidate_quadrant(0.0, 0.0, prior=None)
    assert quadrant is QuadrantLabel.GOLDILOCKS


# --- B4-21: transform history minimums -----------------------------------------


def test_adv_b4_21_change_transform_respects_min_history():
    bundle = pack()
    payroll = next(item for item in bundle.series if item.series_id == "T_PAYROLL")
    short = payroll.model_copy(update={"observations": payroll.observations[-14:]})
    mutated = bundle.model_copy(
        update={
            "series": [
                short if item.series_id == "T_PAYROLL" else item for item in bundle.series
            ]
        }
    )
    registry = FactorBindingRegistry(
        version=1,
        contract="ADVERSARIAL",
        bindings=[
            FactorBinding(
                factor_id="US_PAYROLLS_TREND",
                canonical_series_ids=["T_PAYROLL"],
                transform=FactorTransform(type="CHANGE_CAUSAL_ZSCORE", min_history=20),
                monitoring=MONITORING_LANE,
                formal=BLOCKED_LANE,
            )
        ],
    )
    scores, _ = score_monitoring_factors(mutated, registry=registry)
    assert scores["US_PAYROLLS_TREND"].missing is True
