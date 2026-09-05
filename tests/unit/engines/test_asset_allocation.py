import random

import pytest

from cross_asset.engines.allocation import (
    allocate,
    bounded_projection,
    tactical_bounds,
)
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
    previous = {"A": 0.35, "B": 0.30, "C": 0.20, "CASH": 0.15}
    frozen = allocate({}, strategic, health=False, previous_valid_weight=previous)
    fallback = allocate({}, strategic, health=False)
    assert frozen.status == fallback.status == "FROZEN"
    assert frozen.weights == previous
    assert fallback.weights == strategic


def test_frozen_previous_outside_tactical_envelope_is_projected_with_warning():
    strategic = _strategic()
    previous = {k: 1 / 4 for k in strategic}
    frozen = allocate({}, strategic, health=False, previous_valid_weight=previous)
    assert frozen.status == "FROZEN"
    assert any(
        "previous_valid_allocation_outside_current_constraints_projected" in warning
        for warning in frozen.warnings
    )
    for asset, weight in frozen.weights.items():
        assert strategic[asset] - 0.10 - 1e-9 <= weight <= strategic[asset] + 0.10 + 1e-9
        assert 0.0 - 1e-9 <= weight <= 0.5 + 1e-9
    assert sum(frozen.weights.values()) == pytest.approx(1)


def test_frozen_previous_with_mismatched_universe_falls_back_to_strategic():
    strategic = _strategic()
    frozen = allocate(
        {},
        strategic,
        health=False,
        previous_valid_weight={"A": 0.4, "B": 0.3, "C": 0.2, "OLD": 0.1},
    )
    assert frozen.status == "FROZEN"
    assert set(frozen.weights) == set(strategic)
    assert any(
        "previous_valid_allocation_keys_differ_from_current_universe" in warning
        for warning in frozen.warnings
    )


def test_extreme_scores_keep_final_weight_inside_tactical_envelope():
    strategic = {
        "CN_EQ": 0.25,
        "HK_EQ": 0.10,
        "US_EQ": 0.20,
        "CN_BOND": 0.20,
        "GOLD": 0.10,
        "COMMODITY": 0.05,
        "CASH": 0.10,
    }
    scores = {k: (2 if k == "CN_EQ" else -2) for k in strategic}
    result = allocate(scores, strategic, max_tilt=0.10, min_weight=0.0, max_weight=0.5)
    assert result.status == "ACTIVE"
    assert result.weights["CN_EQ"] <= 0.35 + 1e-9
    for asset, weight in result.weights.items():
        assert abs(weight - strategic[asset]) <= 0.10 + 1e-9
        assert 0.0 - 1e-9 <= weight <= 0.5 + 1e-9
    assert sum(result.weights.values()) == pytest.approx(1)


def test_attribution_tilt_reflects_final_constrained_weights():
    strategic = _strategic()
    scores = {"A": 2, "B": -2, "C": -2, "CASH": -2}
    result = allocate(scores, strategic)
    for asset, attr in result.attribution.items():
        assert attr["constraint_adjusted_tilt"] == pytest.approx(
            result.weights[asset] - strategic[asset]
        )
        assert abs(attr["constraint_adjusted_tilt"]) <= 0.10 + 1e-9


def test_random_active_allocations_stay_in_feasible_set():
    random.seed(19)
    strategic = {
        "CN_EQ": 0.25,
        "HK_EQ": 0.10,
        "US_EQ": 0.20,
        "CN_BOND": 0.20,
        "GOLD": 0.10,
        "COMMODITY": 0.05,
        "CASH": 0.10,
    }
    for _ in range(100):
        scores = {key: random.uniform(-2, 2) for key in strategic}
        result = allocate(scores, strategic, max_tilt=0.10, min_weight=0.0, max_weight=0.5)
        assert result.status == "ACTIVE"
        assert sum(result.weights.values()) == pytest.approx(1)
        for asset, weight in result.weights.items():
            assert 0.0 - 1e-9 <= weight <= 0.5 + 1e-9
            assert abs(weight - strategic[asset]) <= 0.10 + 1e-9


def test_random_strategic_weights_keep_active_allocations_feasible():
    random.seed(23)
    assets = [f"A{i}" for i in range(7)]
    for _ in range(50):
        raw = [random.random() for _ in assets]
        total = sum(raw)
        strategic = {asset: value / total for asset, value in zip(assets, raw)}
        bands = tactical_bounds(
            strategic, max_tilt=0.10, min_weight=0.0, max_weight=0.5
        )
        if any(lower > upper for lower, upper in bands.values()):
            continue
        scores = {asset: random.uniform(-2, 2) for asset in assets}
        result = allocate(scores, strategic, max_tilt=0.10, min_weight=0.0, max_weight=0.5)
        assert result.status == "ACTIVE"
        assert sum(result.weights.values()) == pytest.approx(1)
        for asset, weight in result.weights.items():
            assert 0.0 - 1e-9 <= weight <= 0.5 + 1e-9
            assert abs(weight - strategic[asset]) <= 0.10 + 1e-9


def test_infeasible_tactical_envelope_raises():
    with pytest.raises(ValueError):
        allocate({"A": 1, "B": -1}, {"A": 0.8, "B": 0.2}, max_weight=0.5)
    with pytest.raises(ValueError):
        allocate(
            {"A": 0, "B": 0, "C": 0, "CASH": 0},
            _strategic(),
            min_weight=0.29,
        )
    with pytest.raises(ValueError):
        allocate(
            {"A": 0, "B": 0, "C": 0, "CASH": 0},
            _strategic(),
            max_weight=0.2,
        )


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
