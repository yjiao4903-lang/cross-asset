from pathlib import Path

import pytest

from cross_asset.engines.asset_score import score_asset
from cross_asset.research.component_coverage import (
    compare_score_policies,
    component_coverage,
    declared_wiring,
    effective_weights,
    missing_component_budget,
    snapshot_asset,
    snapshot_from_wiring,
)
from cross_asset.research.factor_registry import audit_factor_registry, load_factor_registry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "config" / "factor_registry.yml"
POLICY = ROOT / "config" / "component_coverage.yml"
ALLOCATION = ROOT / "config" / "allocation.yml"


def test_macro_trend_only_coverage_is_fifty_five():
    components = {"macro": 1.0, "trend": 0.5}
    assert component_coverage(components) == pytest.approx(0.55)
    assert missing_component_budget(components) == pytest.approx(0.45)


def test_renormalize_donates_missing_weight_to_survivors():
    components = {"macro": 1.0, "trend": 0.5}
    weights = effective_weights(components, policy="renormalize_available_components")
    assert weights["macro"] == pytest.approx(0.25 / 0.55)
    assert weights["trend"] == pytest.approx(0.30 / 0.55)
    assert weights["valuation"] is None


def test_reserved_policy_keeps_declared_weights():
    components = {"macro": 1.0, "trend": 0.5}
    weights = effective_weights(components, policy="reserved_declared_weights")
    assert weights["macro"] == pytest.approx(0.25)
    assert weights["trend"] == pytest.approx(0.30)
    assert weights["valuation"] is None
    assert sum(v or 0.0 for v in weights.values()) == pytest.approx(0.55)


def test_snapshot_is_research_state_and_not_admissible():
    snap = snapshot_asset("CN_EQ", {"macro": 1.0, "trend": 0.4}, policy_cfg=_policy())
    assert snap.research_grade == "RESEARCH_STATE"
    assert snap.lane == "RESEARCH_STATE"
    assert snap.allocation_eligibility == "PRODUCTION_RENORMALIZES"
    assert "not_research_admissible" in snap.notes
    assert snap.production_binding_policy == "renormalize_available_components"


def test_personal_lane_does_not_promote_admissible():
    snap = snapshot_asset(
        "US_EQ",
        {"macro": 1.0, "trend": 0.2},
        policy_cfg=_policy(),
        personal=True,
    )
    assert snap.lane == "PERSONAL_WEEKLY"
    assert snap.research_grade != "RESEARCH_ADMISSIBLE"


def test_full_components_are_allocation_candidate_not_bound():
    components = {
        "macro": 1.0,
        "trend": 1.0,
        "valuation": 0.2,
        "carry": 0.1,
        "risk": -0.3,
        "structure": 0.0,
    }
    snap = snapshot_asset("US_EQ", components, policy_cfg=_policy())
    assert snap.coverage == pytest.approx(1.0)
    assert snap.research_grade == "ALLOCATION_CANDIDATE"
    assert snap.allocation_eligibility == "CANDIDATE_NOT_BOUND"
    assert snap.lane == "RESEARCH_STATE"


def test_missing_trend_stays_below_allocation_candidate():
    snap = snapshot_asset("GOLD", {"macro": 1.0, "valuation": 0.2}, policy_cfg=_policy())
    assert "trend" in snap.missing
    assert snap.research_grade == "RESEARCH_STATE"


def test_score_asset_behavior_unchanged_by_diagnostics():
    components = {"macro": 1.0, "trend": 1.0}
    before = score_asset("CN_EQ", components)
    compare_score_policies("CN_EQ", components)
    after = score_asset("CN_EQ", components)
    assert after.score == before.score
    assert after.coverage == before.coverage == pytest.approx(0.55)


def test_reserved_magnitude_shrinks_when_components_missing():
    components = {"macro": 1.0, "trend": 1.0}
    contrast = compare_score_policies("CN_EQ", components)
    assert contrast["renormalized_score"] == pytest.approx(1.0)
    assert contrast["reserved_magnitude_score"] == pytest.approx(0.55)
    assert contrast["bound_to_production"] == "renormalized_score"


def test_declared_wiring_matches_allocation_map():
    wiring = declared_wiring(ALLOCATION)
    assert wiring["CN_EQ"]["macro"] is True
    assert wiring["CN_EQ"]["trend"] is True
    assert wiring["CN_EQ"]["valuation"] is False
    assert wiring["CASH"]["macro"] is False
    assert wiring["CASH"]["trend"] is False


def test_wiring_snapshot_does_not_need_market_data():
    report = snapshot_from_wiring(allocation_path=ALLOCATION, policy_path=POLICY)
    assert report["status"] == "DIAGNOSTIC"
    assert report["research_admissible"] is False
    assert report["universe_grade"] == "RESEARCH_STATE"
    by_asset = {row["asset_id"]: row for row in report["assets"]}
    assert by_asset["CN_EQ"]["coverage"] == pytest.approx(0.55)
    assert by_asset["CASH"]["coverage"] == pytest.approx(0.0)
    assert by_asset["CASH"]["research_grade"] == "INSUFFICIENT"


def test_registry_g0_specs_load_and_block_production():
    specs = load_factor_registry(REGISTRY)
    audit = audit_factor_registry(REGISTRY)
    assert audit.status == "G0_READY"
    assert audit.factor_count == len(specs)
    assert len(specs) >= 8
    assert audit.research_admissible == ()
    assert all(not spec.production_allocation for spec in specs.values())
    assert all(spec.admission_gate == "G0" for spec in specs.values())
    assert all(spec.g0_complete() for spec in specs.values())


def _policy():
    import yaml

    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))
