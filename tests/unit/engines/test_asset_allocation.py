import random

import pytest

from cross_asset.engines.allocation import allocate, bounded_projection
from cross_asset.engines.asset_score import confidence_score, score_asset


def _strategic():
    return {"A": 0.4, "B": 0.3, "C": 0.2, "CASH": 0.1}


def test_asset_score_missing_aware_and_bounded():
    result = score_asset("A", {"macro": 99, "trend": None}, confidence=2)
    assert -2 <= result.score <= 2
    assert result.contributions["trend"] is None
    assert result.confidence == pytest.approx(0.25)
    assert result.coverage == pytest.approx(0.25)
    assert score_asset("A", {}).score is None


def test_confidence_clips_and_decreases():
    assert confidence_score(2, 2, 2, 2) == 1
    assert confidence_score(0.5, 1, 1) < confidence_score(1, 1, 1)


def test_allocation_constraints_sum_and_attribution():
    strategic = _strategic()
    result = allocate({k: 2 for k in strategic}, strategic, min_weight=0.05, max_weight=0.6)
    assert result.status == "ACTIVE"
    assert sum(result.weights.values()) == pytest.approx(1)
    assert all(0.05 <= value <= 0.6 for value in result.weights.values())
    for asset, attr in result.attribution.items():
        assert attr["constraint_adjusted_tilt"] == pytest.approx(
            result.weights[asset] - strategic[asset]
        )
        assert attr["projection_adjustment"] == pytest.approx(
            result.weights[asset] - attr["pre_projection_weight"]
        )


def test_low_confidence_shrinks_tactical_tilt():
    strategic = _strategic()
    high = allocate(
        {k: type("S", (), {"score": 2, "confidence": 1})() for k in strategic}, strategic
    )
    low = allocate(
        {k: type("S", (), {"score": 2, "confidence": 0})() for k in strategic}, strategic
    )
    assert abs(low.attribution["A"]["confidence_adjusted_tilt"]) < abs(
        high.attribution["A"]["confidence_adjusted_tilt"]
    )


def test_frozen_uses_previous_then_strategic_fallback():
    strategic = _strategic()
    previous = {k: 1 / 4 for k in strategic}
    frozen = allocate({}, strategic, health=False, previous_valid_weight=previous)
    fallback = allocate({}, strategic, health=False)
    assert frozen.status == fallback.status == "FROZEN"
    assert frozen.weights == previous
    assert fallback.weights == strategic


def test_infeasible_constraints_raise():
    with pytest.raises(ValueError):
        bounded_projection({"A": 0.5, "B": 0.5}, 0.6, 0.7)


def test_bounded_projection_random_feasible_cases():
    random.seed(7)
    for _ in range(25):
        values = {f"A{i}": random.random() for i in range(5)}
        projected = bounded_projection(values, 0.05, 0.6)
        assert sum(projected.values()) == pytest.approx(1)
        assert all(0.05 - 1e-10 <= x <= 0.6 + 1e-10 for x in projected.values())



def test_component_confidence_and_weighted_coverage_reduce_asset_confidence():
    result = score_asset(
        "A",
        {
            "macro": {"score": 1.0, "confidence": 0.5},
            "trend": {"score": 1.0, "confidence": 1.0},
        },
    )
    assert result.coverage == pytest.approx(0.55)
    expected_quality = (0.25 * 0.5 + 0.30 * 1.0) / 0.55
    assert result.confidence == pytest.approx(0.55 * expected_quality)
