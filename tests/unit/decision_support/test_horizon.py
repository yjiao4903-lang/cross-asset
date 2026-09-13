"""Issue #114 Scope B tests: horizon separation is enforced, never silent."""

import pytest

from cross_asset.decision_support.enums import HorizonClass
from cross_asset.decision_support.horizon import (
    HorizonMixingError,
    SubfactorScore,
    aggregate_cluster_horizon,
    aggregate_context,
    aggregate_horizon,
    separate_by_horizon,
)


def _cyc(factor_id: str, score: float) -> SubfactorScore:
    return SubfactorScore(factor_id=factor_id, horizon=HorizonClass.CYCLICAL, score=score)


def _tac(factor_id: str, score: float) -> SubfactorScore:
    return SubfactorScore(factor_id=factor_id, horizon=HorizonClass.TACTICAL, score=score)


def _ctx(factor_id: str, score: float) -> SubfactorScore:
    return SubfactorScore(
        factor_id=factor_id, horizon=HorizonClass.STRUCTURAL_CONTEXT, score=score
    )


def test_mixed_horizon_aggregation_rejected():
    mixed = [_cyc("growth_a", 1.0), _tac("momentum_a", 1.0)]
    with pytest.raises(HorizonMixingError, match="horizon mixing rejected"):
        aggregate_horizon(mixed, horizon=HorizonClass.CYCLICAL)


def test_structural_context_never_aggregated_into_macro_score():
    overlays = [_ctx("erp", 1.0), _cyc("growth_a", 1.0)]
    with pytest.raises(HorizonMixingError, match="STRUCTURAL_CONTEXT"):
        aggregate_horizon(overlays, horizon=HorizonClass.CYCLICAL)


def test_context_only_aggregation_is_separate():
    agg = aggregate_context([_ctx("erp", 1.0), _ctx("valuation", -1.0)])
    assert agg.horizon is HorizonClass.STRUCTURAL_CONTEXT
    assert agg.score == 0.0


def test_homogeneous_aggregation_works():
    agg = aggregate_cluster_horizon(
        [_cyc("a", 0.5), _cyc("b", -1.0)], horizon=HorizonClass.CYCLICAL
    )
    assert agg.score == -0.25
    assert agg.coverage == 1.0


def test_separate_by_horizon_splits_groups():
    groups = separate_by_horizon([_cyc("a", 1.0), _tac("b", -0.5), _ctx("c", 2.0)])
    assert set(groups) == {
        HorizonClass.CYCLICAL,
        HorizonClass.TACTICAL,
        HorizonClass.STRUCTURAL_CONTEXT,
    }
    assert [s.factor_id for s in groups[HorizonClass.CYCLICAL]] == ["a"]


def test_missing_inputs_preserved_not_zero_filled():
    scores = [
        _cyc("a", 0.5),
        SubfactorScore(factor_id="b", horizon=HorizonClass.CYCLICAL, missing=True),
    ]
    agg = aggregate_cluster_horizon(scores, horizon=HorizonClass.CYCLICAL)
    assert agg.score == 0.5
    assert agg.coverage == 0.5
    assert agg.missing == ["b"]
    assert agg.confidence < 1.0
    with pytest.raises(ValueError, match="missing"):
        SubfactorScore(factor_id="b", horizon=HorizonClass.CYCLICAL, missing=True).effective_score()
