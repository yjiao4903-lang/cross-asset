"""Issue #114 Scope A/D tests: snapshot contract and taxonomy config."""

from datetime import date, datetime

import pytest

from cross_asset.decision_support.enums import EvidenceLane, HorizonClass
from cross_asset.decision_support.snapshot import (
    AssetViewV0,
    DashboardSnapshotV0,
    SnapshotMetadata,
    WeeklyChange,
)
from cross_asset.decision_support.taxonomy import (
    CANONICAL_FAMILIES,
    load_taxonomy,
)
from cross_asset.decision_support.weekly import (
    AssetViewDelta,
    InformationSetDelta,
    MacroStateDelta,
    MarketConditionDelta,
)


def _minimal_snapshot() -> DashboardSnapshotV0:
    from cross_asset.decision_support.fixtures import (
        _benign_scenario,
        _build_snapshot,
    )

    config = load_taxonomy()
    return _build_snapshot(_benign_scenario(config), config)


def test_taxonomy_has_exactly_eight_canonical_families():
    config = load_taxonomy()
    assert [family.family_id for family in config.families] == list(CANONICAL_FAMILIES)


def test_taxonomy_v1_is_compact_not_the_42_backlog():
    config = load_taxonomy()
    subfactors = config.subfactors()
    assert 15 <= len(subfactors) <= 30
    for sub in subfactors:
        assert HorizonClass(sub.horizon) in set(HorizonClass)
        assert sub.binding_status == "UNBOUND"


def test_taxonomy_all_eight_families_have_subfactors():
    config = load_taxonomy()
    for family in config.families:
        assert family.subfactors, f"{family.family_id} has no V1 subfactors"


def test_asset_rules_cover_all_target_assets():
    config = load_taxonomy()
    assets = {rule.asset for rule in config.asset_rules}
    assert assets == {
        "CN_EQ",
        "HK_EQ",
        "US_EQ",
        "CN_BOND",
        "GOLD",
        "COPPER",
        "USD_CNY",
        "CASH",
    }


def test_legacy_factor_config_untouched():

    from cross_asset.decision_support.taxonomy import DEFAULT_CONFIG_PATH

    assert DEFAULT_CONFIG_PATH.name == "decision_support_v2.yml"
    legacy = DEFAULT_CONFIG_PATH.parent / "factors.yml"
    assert legacy.exists()
    legacy_text = legacy.read_text(encoding="utf-8")
    assert "decision_support" not in legacy_text


def test_snapshot_roundtrip_serialization_stable():
    snapshot = _minimal_snapshot()
    raw = snapshot.to_json()
    restored = DashboardSnapshotV0.from_json(raw)
    assert restored == snapshot
    assert restored.to_json() == raw


def test_snapshot_serialization_is_deterministic():
    assert _minimal_snapshot().to_json() == _minimal_snapshot().to_json()


def test_snapshot_top_level_contract_is_render_oriented():
    snapshot = _minimal_snapshot()
    for field in (
        "metadata",
        "macro_climate",
        "investment_climate",
        "clusters",
        "weekly_change",
        "regime",
        "asset_views",
        "cross_asset_pulse",
        "executive_brief",
        "data_health_summary",
        "details",
    ):
        assert hasattr(snapshot, field), field
    # Full lineage lives under details, not as top-level noise.
    assert isinstance(snapshot.details, dict)


def test_snapshot_weekly_change_has_four_surfaces():
    snapshot = _minimal_snapshot()
    assert isinstance(snapshot.weekly_change, WeeklyChange)
    assert isinstance(snapshot.weekly_change.information_set_delta, InformationSetDelta)
    assert isinstance(snapshot.weekly_change.macro_state_delta, MacroStateDelta)
    assert isinstance(snapshot.weekly_change.market_condition_delta, MarketConditionDelta)
    assert isinstance(snapshot.weekly_change.asset_view_delta, AssetViewDelta)


def test_fixture_cannot_be_labelled_formal_oos():
    from cross_asset.decision_support.fixtures import build_benign_snapshot

    # R1 blocker 6: synthetic fixtures are hard-barred from FORMAL_OOS; there
    # is no evidence-string escape path any more.
    with pytest.raises(ValueError, match="FIXTURE_MONITORING_ONLY"):
        build_benign_snapshot(lane=EvidenceLane.FORMAL_OOS)
    with pytest.raises(TypeError):
        build_benign_snapshot(lane=EvidenceLane.FORMAL_OOS, formal_oos_evidence="anything")


def test_controlled_vocabulary_rejects_invalid_values():
    from datetime import UTC, date, datetime

    from pydantic import ValidationError

    from cross_asset.decision_support.horizon import SubfactorScore
    from cross_asset.decision_support.snapshot import (
        AssetViewV0,
        DataHealthSummary,
        SnapshotMetadata,
    )

    base_meta = {
        "snapshot_id": "s1",
        "as_of": date(2026, 9, 4),
        "decision_time": datetime(2026, 9, 5, tzinfo=UTC),
        "run_id": "r1",
        "model_version": "m1",
    }
    with pytest.raises(ValidationError, match="lane"):
        SnapshotMetadata(**base_meta, lane="STAGING_LANE")
    with pytest.raises(ValidationError, match="horizon"):
        SubfactorScore(factor_id="x", horizon="QUARTERLY", score=0.1)
    base_view = {
        "asset": "US_EQ",
        "macro_bias": 0,
        "stance": 0,
        "prior_stance": 0,
    }
    with pytest.raises(ValidationError, match="market_confirmation"):
        AssetViewV0(**base_view, market_confirmation="MAYBE_CONFIRMED")
    with pytest.raises(ValidationError, match="overall"):
        DataHealthSummary(overall="BROKEN_HEALTH")


def test_asset_view_stances_are_bounded():
    snapshot = _minimal_snapshot()
    for view in snapshot.asset_views:
        assert isinstance(view, AssetViewV0)
        assert -2 <= view.macro_bias <= 2
        assert -2 <= view.stance <= 2
        assert -2 <= view.prior_stance <= 2


def test_snapshot_metadata_shape():
    snapshot = _minimal_snapshot()
    metadata = snapshot.metadata
    assert isinstance(metadata, SnapshotMetadata)
    assert metadata.snapshot_version == "DashboardSnapshotV0"
    assert metadata.as_of == date(2026, 9, 4)
    assert isinstance(metadata.decision_time, datetime)
    assert metadata.run_id and metadata.model_version
