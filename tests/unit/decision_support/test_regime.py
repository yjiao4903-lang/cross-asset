"""Issue #114 Scope E tests: interpretable regime with deterministic hysteresis."""

from cross_asset.decision_support.enums import QuadrantLabel
from cross_asset.decision_support.regime import RegimeEngine, evaluate_lens_disagreement
from cross_asset.decision_support.snapshot import RegimeState


def _update(
    engine: RegimeEngine,
    prior: RegimeState | None,
    growth: float,
    inflation: float,
) -> RegimeState:
    return engine.update(
        growth_score=growth,
        growth_direction="RISING" if growth > 0 else "FALLING",
        inflation_score=inflation,
        inflation_direction="RISING" if inflation > 0 else "FALLING",
        inflation_state="HIGH" if inflation > 0.4 else "MODERATE",
        prior=prior,
    )


def test_initial_state_without_prior():
    engine = RegimeEngine(min_dwell_weeks=3)
    state = _update(engine, None, 0.5, -0.3)
    assert state.resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    assert state.dwell_weeks == 1
    assert state.transition_flag is False


def test_hysteresis_blocks_premature_transition():
    engine = RegimeEngine(min_dwell_weeks=3)
    state = _update(engine, None, 0.5, -0.3)
    # Candidate flips to stagflation-risk but has not persisted long enough.
    state = _update(engine, state, -0.6, 0.6)
    assert state.resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    assert state.transition_flag is False
    assert state.dwell_weeks == 2
    state = _update(engine, state, -0.6, 0.6)
    assert state.resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    assert state.dwell_weeks == 3


def test_transition_after_min_dwell():
    engine = RegimeEngine(min_dwell_weeks=3)
    state = _update(engine, None, 0.5, -0.3)
    state = _update(engine, state, -0.6, 0.6)
    state = _update(engine, state, -0.6, 0.6)
    state = _update(engine, state, -0.6, 0.6)
    assert state.resolved_quadrant() is QuadrantLabel.STAGFLATION_RISK
    assert state.transition_flag is True
    assert state.dwell_weeks == 1
    # Subsequent stable weeks increment dwell without transition flags.
    state = _update(engine, state, -0.6, 0.6)
    assert state.resolved_quadrant() is QuadrantLabel.STAGFLATION_RISK
    assert state.transition_flag is False
    assert state.dwell_weeks == 2


def test_deadband_inherits_prior_axis():
    engine = RegimeEngine(axis_threshold=0.25, min_dwell_weeks=3)
    state = _update(engine, None, 0.5, -0.3)
    # Growth inside the deadband must not flip the quadrant on its own.
    state = _update(engine, state, 0.1, -0.1)
    assert state.resolved_quadrant() is QuadrantLabel.GOLDILOCKS


def test_quadrant_labels_cover_four_combinations():
    engine = RegimeEngine(min_dwell_weeks=1)
    assert _update(engine, None, 0.5, -0.5).resolved_quadrant() is QuadrantLabel.GOLDILOCKS
    assert _update(engine, None, 0.5, 0.5).resolved_quadrant() is QuadrantLabel.REFLATION
    assert (
        _update(engine, None, -0.5, 0.5).resolved_quadrant() is QuadrantLabel.STAGFLATION_RISK
    )
    assert (
        _update(engine, None, -0.5, -0.5).resolved_quadrant()
        is QuadrantLabel.DISINFLATIONARY_SLUMP
    )


def test_engine_is_deterministic():
    def run() -> list[tuple[str, int, bool]]:
        engine = RegimeEngine(min_dwell_weeks=3)
        state = None
        outputs = []
        for growth, inflation in [(0.5, -0.3), (-0.6, 0.6), (-0.6, 0.6), (-0.6, 0.6)]:
            state = _update(engine, state, growth, inflation)
            outputs.append((state.quadrant_label, state.dwell_weeks, state.transition_flag))
        return outputs

    assert run() == run()


def test_lens_disagreement_flag():
    aligned = evaluate_lens_disagreement({"survey": 0.4, "market": 0.6}, threshold=1.0)
    assert aligned.flag is False
    split = evaluate_lens_disagreement({"survey": -0.8, "market": 0.8}, threshold=1.0)
    assert split.flag is True
    assert "survey" in split.summary and "market" in split.summary
