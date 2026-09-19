"""REAL-SNAPSHOT-V1 producer for canonical MONITORING observations.

The producer is intentionally provider-neutral. Acquisition, calendars,
freshness computation and catalog population belong to Issue #125; this module
consumes their canonical/lane-labelled output. It reuses the accepted
Decision Support v2 horizon, regime, weekly-change and asset-gate primitives.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from cross_asset.features.normalization import latest_causal_zscore
from cross_asset.features.trend import multi_horizon_trend_signal

from .asset_rules import AssetGateResult, build_asset_gate
from .binding import FactorBinding, FactorBindingRegistry, load_factor_bindings
from .climate import derive_climate_components, derive_investment_climate, derive_macro_climate
from .enums import (
    AxisDirection,
    DataHealthStatus,
    EvidenceLane,
    HorizonClass,
    InflationState,
    InformationSetStatus,
    ReleaseEventType,
)
from .factor_transforms import (
    core_cpi_3m6m_annualized_trend,
    payroll_3m6m_smoothed_momentum,
)
from .horizon import HorizonAggregate, SubfactorScore, aggregate_cluster_horizon, aggregate_context
from .regime import RegimeEngine
from .snapshot import (
    AssetViewV0,
    ClusterView,
    CrossAssetPulse,
    DashboardSnapshotV0,
    DataHealthSummary,
    ExecutiveBrief,
    PulseEntry,
    SnapshotMetadata,
    WeeklyChange,
)
from .taxonomy import DecisionSupportConfig, load_taxonomy, signed_score
from .weekly import (
    AssetStanceChange,
    AssetViewDelta,
    ReleaseEvent,
    build_information_set_delta,
    build_macro_state_delta,
    build_market_condition_delta,
    build_market_move,
)

MODEL_VERSION = "decision-support-v2-real-snapshot-v1"
_ALLOWED_SERIES_STATUS = {"FRESH", "STALE", "MISSING", "BLOCKED"}
_HEALTHY_SERIES_STATUS = {"FRESH", "STALE"}


class MonitoringObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_date: date
    available_at: datetime
    value: float
    source_ref: str = ""


class MonitoringSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_id: str
    status: str = "FRESH"
    observations: list[MonitoringObservation] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MonitoringRunLineage(BaseModel):
    """Subset of accepted WorkbenchRun identity needed by the snapshot."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    decision_time: datetime
    data_cutoff: date
    source_mode: str
    config_identity: str


class MonitoringMarketMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: str
    metric_class: str
    prior_value: float
    current_value: float


class MonitoringObservationPack(BaseModel):
    """Provider-neutral canonical input contract for REAL-SNAPSHOT-V1."""

    model_config = ConfigDict(extra="forbid")

    lane: EvidenceLane = EvidenceLane.MONITORING
    origin: str = "CANONICAL_MONITORING"
    as_of: date
    lineage: MonitoringRunLineage
    series: list[MonitoringSeries]
    release_events: list[ReleaseEvent] = Field(default_factory=list)
    expected_releases: dict[str, date] = Field(default_factory=dict)
    market_moves: list[MonitoringMarketMove] = Field(default_factory=list)
    pulse: list[PulseEntry] = Field(default_factory=list)


class MonitoringSnapshotBlocked(ValueError):
    """Raised when a truthful snapshot cannot be produced without fabrication."""


def _validate_pack(pack: MonitoringObservationPack) -> None:
    if pack.lane is not EvidenceLane.MONITORING:
        raise ValueError("REAL_SNAPSHOT_V1_REQUIRES_MONITORING_LANE")
    if pack.origin != "CANONICAL_MONITORING":
        raise ValueError("REAL_SNAPSHOT_V1_REJECTS_FIXTURE_OR_UNKNOWN_ORIGIN")
    if pack.lineage.source_mode != "LIVE":
        raise ValueError("REAL_SNAPSHOT_V1_REQUIRES_LIVE_WORKBENCH_LINEAGE")
    seen: set[str] = set()
    for series in pack.series:
        if series.series_id in seen:
            raise ValueError(f"duplicate monitoring series: {series.series_id}")
        seen.add(series.series_id)
        if series.status not in _ALLOWED_SERIES_STATUS:
            raise ValueError(f"invalid monitoring series status: {series.series_id}:{series.status}")
        ordered = sorted(series.observations, key=lambda row: (row.observation_date, row.available_at))
        if ordered != series.observations:
            raise ValueError(f"monitoring observations not ordered: {series.series_id}")
        if any(row.available_at > pack.lineage.decision_time for row in series.observations):
            raise ValueError(f"observation available after decision_time: {series.series_id}")
        if any(row.observation_date > pack.lineage.data_cutoff for row in series.observations):
            raise ValueError(f"observation after data_cutoff: {series.series_id}")


def _series_map(pack: MonitoringObservationPack) -> dict[str, MonitoringSeries]:
    return {series.series_id: series for series in pack.series}


def _pandas_series(series: MonitoringSeries) -> pd.Series:
    return pd.Series(
        [row.value for row in series.observations],
        index=pd.to_datetime([row.observation_date for row in series.observations]),
        dtype=float,
    )


def _causal_score(values: pd.Series, *, min_history: int) -> float | None:
    if values.empty:
        return None
    return latest_causal_zscore(values, min_history=min_history, clip=2.0)


def _transform_binding(
    binding: FactorBinding,
    source: dict[str, MonitoringSeries],
) -> tuple[float | None, float, bool, str]:
    required = [source.get(series_id) for series_id in binding.canonical_series_ids]
    missing_ids = [
        series_id
        for series_id, series in zip(binding.canonical_series_ids, required, strict=True)
        if series is None or series.status not in _HEALTHY_SERIES_STATUS or not series.observations
    ]
    if missing_ids:
        return None, 0.0, False, f"canonical series unavailable: {','.join(missing_ids)}"

    resolved = [series for series in required if series is not None]
    stale = any(series.status == "STALE" for series in resolved)
    transform = binding.transform
    typ = transform.type
    score: float | None
    confidence = 1.0

    if typ == "LEVEL_CAUSAL_ZSCORE":
        score = _causal_score(_pandas_series(resolved[0]), min_history=transform.min_history)
    elif typ == "CHANGE_CAUSAL_ZSCORE":
        changes = _pandas_series(resolved[0]).diff()
        score = _causal_score(changes, min_history=transform.min_history)
    elif typ == "YOY_CAUSAL_ZSCORE":
        values = _pandas_series(resolved[0])
        yoy = values.pct_change(periods=transform.lag_periods, fill_method=None) * 100.0
        score = _causal_score(yoy, min_history=transform.min_history)
    elif typ == "PAYROLL_3M6M_SMOOTHED_MOMENTUM":
        momentum = payroll_3m6m_smoothed_momentum(_pandas_series(resolved[0]))
        score = _causal_score(momentum, min_history=transform.min_history)
    elif typ == "CORE_CPI_3M6M_ANNUALIZED_TREND":
        trend = core_cpi_3m6m_annualized_trend(_pandas_series(resolved[0]))
        score = _causal_score(trend, min_history=transform.min_history)
    elif typ == "SPREAD_CAUSAL_ZSCORE":
        if len(resolved) != 2:
            raise ValueError(f"SPREAD_CAUSAL_ZSCORE needs two series: {binding.factor_id}")
        left, right = _pandas_series(resolved[0]).align(_pandas_series(resolved[1]), join="inner")
        score = _causal_score(left - right, min_history=transform.min_history)
    elif typ == "TREND_63D":
        result = multi_horizon_trend_signal(
            _pandas_series(resolved[0]),
            periods={"ret_3m": 63},
            weights={"ret_3m": 1.0},
        )
        score = result.score
        confidence = result.confidence
    else:
        raise ValueError(f"unsupported transform: {typ}")

    if score is None:
        return None, 0.0, stale, "transform unavailable: insufficient causal history"
    if stale:
        confidence *= 0.5
    return float(score), round(confidence, 4), stale, ""


def score_monitoring_factors(
    pack: MonitoringObservationPack,
    *,
    taxonomy: DecisionSupportConfig | None = None,
    registry: FactorBindingRegistry | None = None,
) -> tuple[dict[str, SubfactorScore], dict[str, dict[str, Any]]]:
    """Bind canonical MONITORING series to accepted taxonomy factors."""

    _validate_pack(pack)
    taxonomy = taxonomy or load_taxonomy()
    registry = registry or load_factor_bindings(taxonomy=taxonomy)
    source = _series_map(pack)
    bindings = registry.by_factor()
    scores: dict[str, SubfactorScore] = {}
    statuses: dict[str, dict[str, Any]] = {}

    for spec in taxonomy.subfactors():
        binding = bindings.get(spec.factor_id)
        if binding is None or binding.monitoring.status != "BOUND":
            scores[spec.factor_id] = SubfactorScore(
                factor_id=spec.factor_id,
                horizon=spec.horizon,
                score=None,
                confidence=0.0,
                coverage=0.0,
                missing=True,
                note="monitoring binding unbound",
            )
            statuses[spec.factor_id] = {
                "monitoring": "UNBOUND",
                "formal": binding.formal.status if binding else "UNBOUND",
                "missing": True,
                "stale": False,
                "reason": "monitoring binding unbound",
            }
            continue

        native_score, confidence, stale, reason = _transform_binding(binding, source)
        if native_score is None:
            scores[spec.factor_id] = SubfactorScore(
                factor_id=spec.factor_id,
                horizon=spec.horizon,
                score=None,
                confidence=0.0,
                coverage=0.0,
                missing=True,
                stale=stale,
                note=reason,
            )
            statuses[spec.factor_id] = {
                "monitoring": binding.monitoring.status,
                "formal": binding.formal.status,
                "missing": True,
                "stale": stale,
                "reason": reason,
            }
            continue

        economic_score = signed_score(spec, native_score)
        scores[spec.factor_id] = SubfactorScore(
            factor_id=spec.factor_id,
            horizon=spec.horizon,
            score=economic_score,
            confidence=confidence,
            coverage=1.0,
            missing=False,
            stale=stale,
            note="canonical monitoring binding",
        )
        statuses[spec.factor_id] = {
            "monitoring": binding.monitoring.status,
            "formal": binding.formal.status,
            "missing": False,
            "stale": stale,
            "reason": "",
        }
    return scores, statuses


def _family_aggregates(
    scores: dict[str, SubfactorScore],
    taxonomy: DecisionSupportConfig,
) -> dict[tuple[str, HorizonClass], HorizonAggregate]:
    aggregates: dict[tuple[str, HorizonClass], HorizonAggregate] = {}
    for family in taxonomy.families:
        groups: dict[HorizonClass, list[SubfactorScore]] = {}
        for spec in family.subfactors:
            groups.setdefault(spec.resolved_horizon(), []).append(scores[spec.factor_id])
        for horizon, entries in groups.items():
            if horizon is HorizonClass.STRUCTURAL_CONTEXT:
                aggregates[(family.family_id, horizon)] = aggregate_context(entries)
            else:
                aggregates[(family.family_id, horizon)] = aggregate_cluster_horizon(
                    entries, horizon=horizon
                )
    return aggregates


def _direction(delta: float | None) -> AxisDirection:
    if delta is None or abs(delta) <= 0.05:
        return AxisDirection.FLAT
    return AxisDirection.RISING if delta > 0 else AxisDirection.FALLING


def _inflation_state(score: float) -> InflationState:
    if score >= 0.4:
        return InflationState.HIGH
    if score <= -0.4:
        return InflationState.LOW
    return InflationState.MODERATE


def _economic_week_id(value: date) -> str:
    """Stable economic-step identity: Monday date of the product decision week."""

    return (value - timedelta(days=value.weekday())).isoformat()


def _snapshot_economic_week_id(snapshot: DashboardSnapshotV0) -> str:
    explicit = snapshot.details.get("economic_week_id")
    if explicit:
        return str(explicit)
    raw_cutoff = snapshot.details.get("data_cutoff")
    if raw_cutoff:
        try:
            return _economic_week_id(date.fromisoformat(str(raw_cutoff)[:10]))
        except ValueError:
            pass
    return _economic_week_id(snapshot.metadata.as_of)


def _normalized_regime_history(
    previous_snapshot: DashboardSnapshotV0 | None,
    *,
    current_week_id: str,
) -> list[dict[str, Any]]:
    """Return causal, de-duplicated economic-week history.

    Pre-F04 rows had no economic-step identity and therefore cannot safely be
    replayed as multiple dwell weeks. Conservatively retain only the last such
    row, assigning it to the previous snapshot's own economic week; earlier
    unkeyed rows are dropped rather than guessed.
    """

    if previous_snapshot is None:
        return []
    by_week: dict[str, dict[str, Any]] = {}
    legacy_last: dict[str, Any] | None = None
    for raw in previous_snapshot.details.get("regime_input_history", []):
        item = dict(raw)
        week_id = item.get("economic_week_id")
        if not week_id:
            legacy_last = item
            continue
        resolved = str(week_id)
        if resolved <= current_week_id:
            item["economic_week_id"] = resolved
            by_week[resolved] = item

    if legacy_last is not None:
        previous_week_id = _snapshot_economic_week_id(previous_snapshot)
        if previous_week_id <= current_week_id and previous_week_id not in by_week:
            migrated = dict(legacy_last)
            migrated["economic_week_id"] = previous_week_id
            by_week[previous_week_id] = migrated

    return [by_week[week_id] for week_id in sorted(by_week)]


def _cluster_views(
    current: dict[tuple[str, HorizonClass], HorizonAggregate],
    previous: dict[tuple[str, HorizonClass], HorizonAggregate] | None,
) -> list[ClusterView]:
    views: list[ClusterView] = []
    for (family, horizon), aggregate in sorted(current.items()):
        prior = previous.get((family, horizon)) if previous else None
        delta = (
            round(aggregate.score - prior.score, 4)
            if aggregate.score is not None and prior is not None and prior.score is not None
            else None
        )
        if aggregate.missing and not aggregate.contributors:
            health = DataHealthStatus.MISSING
        elif aggregate.missing or aggregate.stale:
            health = DataHealthStatus.PARTIAL
        else:
            health = DataHealthStatus.OK
        views.append(
            ClusterView(
                cluster_id=f"{family}@{horizon.value}",
                family=family,
                horizon=horizon,
                score=aggregate.score,
                weekly_delta=delta,
                direction=_direction(delta),
                confidence=aggregate.confidence,
                coverage=aggregate.coverage,
                missing_factors=aggregate.missing,
                stale_factors=aggregate.stale,
                freshness_status=health,
            )
        )
    return views


def _previous_scores(
    previous_snapshot: DashboardSnapshotV0 | None,
    taxonomy: DecisionSupportConfig,
) -> dict[str, SubfactorScore] | None:
    if previous_snapshot is None:
        return None
    raw_scores = previous_snapshot.details.get("subfactor_scores_current", {})
    raw_statuses = previous_snapshot.details.get("factor_statuses", {})
    result: dict[str, SubfactorScore] = {}
    for spec in taxonomy.subfactors():
        value = raw_scores.get(spec.factor_id)
        status = raw_statuses.get(spec.factor_id, {})
        missing = value is None
        result[spec.factor_id] = SubfactorScore(
            factor_id=spec.factor_id,
            horizon=spec.horizon,
            score=value,
            confidence=float(status.get("confidence", 0.0 if missing else 1.0)),
            coverage=0.0 if missing else 1.0,
            missing=missing,
            stale=bool(status.get("stale", False)),
            note="previous persisted REAL-SNAPSHOT-V1 state",
        )
    return result


def _build_regime(
    current: dict[tuple[str, HorizonClass], HorizonAggregate],
    previous_snapshot: DashboardSnapshotV0 | None,
    taxonomy: DecisionSupportConfig,
    *,
    economic_week_id: str,
):
    growth = current[("GROWTH_ACTIVITY", HorizonClass.CYCLICAL)]
    inflation = current[("INFLATION_COST", HorizonClass.CYCLICAL)]
    if growth.score is None or inflation.score is None:
        raise MonitoringSnapshotBlocked(
            "regime axes unavailable; refusing to synthesize growth/inflation from missing data"
        )

    history = _normalized_regime_history(
        previous_snapshot,
        current_week_id=economic_week_id,
    )
    by_week = {str(item["economic_week_id"]): dict(item) for item in history}
    by_week[economic_week_id] = {
        "economic_week_id": economic_week_id,
        "growth_score": growth.score,
        "inflation_score": inflation.score,
        "confidence": min(growth.confidence, inflation.confidence),
        "coverage": min(growth.coverage, inflation.coverage),
    }
    history = [by_week[week_id] for week_id in sorted(by_week)][-12:]

    engine = RegimeEngine(
        axis_threshold=taxonomy.regime.axis_threshold,
        min_dwell_weeks=taxonomy.regime.min_dwell_weeks,
        lens_disagreement_threshold=taxonomy.regime.lens_disagreement_threshold,
    )
    state = None
    previous_growth: float | None = None
    previous_inflation: float | None = None
    for item in history:
        growth_delta = (
            None if previous_growth is None else float(item["growth_score"]) - previous_growth
        )
        inflation_delta = (
            None
            if previous_inflation is None
            else float(item["inflation_score"]) - previous_inflation
        )
        state = engine.update(
            growth_score=float(item["growth_score"]),
            growth_direction=_direction(growth_delta),
            inflation_score=float(item["inflation_score"]),
            inflation_direction=_direction(inflation_delta),
            inflation_state=_inflation_state(float(item["inflation_score"])),
            prior=state,
            confidence=float(item["confidence"]),
            coverage=float(item["coverage"]),
        )
        previous_growth = float(item["growth_score"])
        previous_inflation = float(item["inflation_score"])
    assert state is not None
    return state, history


def _asset_gates(
    scores: dict[str, SubfactorScore],
    aggregates: dict[tuple[str, HorizonClass], HorizonAggregate],
    taxonomy: DecisionSupportConfig,
) -> dict[str, AssetGateResult]:
    cyclical = {
        family: aggregate.score
        for (family, horizon), aggregate in aggregates.items()
        if horizon is HorizonClass.CYCLICAL
    }
    tactical = {
        factor_id: score.score
        for factor_id, score in scores.items()
        if score.resolved_horizon() is HorizonClass.TACTICAL and not score.missing
    }
    structural = {
        factor_id: score.score
        for factor_id, score in scores.items()
        if score.resolved_horizon() is HorizonClass.STRUCTURAL_CONTEXT and not score.missing
    }
    return {
        rule.asset: build_asset_gate(
            rule,
            cyclical_scores=cyclical,
            tactical_scores=tactical,
            structural_scores=structural,
        )
        for rule in taxonomy.asset_rules
    }


def _asset_views_and_delta(
    gates: dict[str, AssetGateResult],
    previous_snapshot: DashboardSnapshotV0 | None,
    changed_factors: list[str],
    taxonomy: DecisionSupportConfig,
) -> tuple[list[AssetViewV0], AssetViewDelta]:
    previous = {
        str(view.asset): view for view in (previous_snapshot.asset_views if previous_snapshot else [])
    }
    factor_family = {spec.factor_id: spec.family for spec in taxonomy.subfactors()}
    updated_families = sorted({factor_family[fid] for fid in changed_factors if fid in factor_family})
    views: list[AssetViewV0] = []
    deltas: list[AssetStanceChange] = []
    for rule in taxonomy.asset_rules:
        gate = gates[rule.asset]
        prior = previous.get(rule.asset)
        prior_stance = prior.stance if prior is not None else gate.stance
        prior_confidence = prior.confidence if prior is not None else gate.confidence
        views.append(
            AssetViewV0(
                asset=gate.asset,
                macro_bias=gate.macro_bias,
                market_confirmation=gate.market_confirmation,
                valuation_tag=gate.valuation_tag,
                stance=gate.stance,
                prior_stance=prior_stance,
                confidence=gate.confidence,
                drivers=gate.drivers,
                counter_signals=gate.counter_signals,
                invalidator=rule.invalidator,
                data_health=gate.data_health,
            )
        )
        stance_delta = gate.stance - prior_stance
        confidence_delta = round(gate.confidence - prior_confidence, 4)
        if stance_delta or abs(confidence_delta) >= 0.01:
            tags = [f"MARKET_{gate.market_confirmation.value}"]
            tags.extend(f"{family}_UPDATED" for family in updated_families)
            if stance_delta > 0:
                tags.insert(0, "STANCE_UP")
            elif stance_delta < 0:
                tags.insert(0, "STANCE_DOWN")
            deltas.append(
                AssetStanceChange(
                    asset=gate.asset,
                    previous_stance=prior_stance,
                    current_stance=gate.stance,
                    delta=stance_delta,
                    reason_tags=tags,
                    confidence_delta=confidence_delta,
                )
            )
    return views, AssetViewDelta(entries=deltas)


def _data_health(
    clusters: list[ClusterView],
    gates: dict[str, AssetGateResult],
    factor_statuses: dict[str, dict[str, Any]],
) -> DataHealthSummary:
    stale = sorted(factor for factor, state in factor_statuses.items() if state["stale"])
    missing = sorted(factor for factor, state in factor_statuses.items() if state["missing"])
    blockers = [
        f"{asset}: {blocker.source} — {blocker.reason}"
        for asset, gate in sorted(gates.items())
        for blocker in gate.blockers
    ]
    if missing and not any(cluster.score is not None for cluster in clusters):
        overall = DataHealthStatus.MISSING
    elif stale or missing or blockers:
        overall = DataHealthStatus.PARTIAL
    else:
        overall = DataHealthStatus.OK
    return DataHealthSummary(
        overall=overall,
        stale_components=stale,
        missing_components=missing,
        blockers=blockers,
    )


def _snapshot_id(pack: MonitoringObservationPack, registry_version: int, taxonomy_version: int) -> str:
    payload = {
        "pack": pack.model_dump(mode="json"),
        "binding_registry_version": registry_version,
        "taxonomy_version": taxonomy_version,
        "model_version": MODEL_VERSION,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"dsv0-monitoring-{pack.as_of.isoformat().replace('-', '')}-{digest}"


def _series_observation_identities(series: MonitoringSeries) -> list[dict[str, Any]]:
    """Capture-time observation identities for one canonical series.

    DB-built packs record the authoritative identity (source, source_series_id)
    in provenance; hand-built diagnostic packs fall back to their observations.
    """
    recorded = series.provenance.get("observations")
    if isinstance(recorded, list) and recorded:
        return [item for item in recorded if isinstance(item, dict)]
    return [
        {
            "observation_date": observation.observation_date.isoformat(),
            "available_at": observation.available_at.isoformat(),
            "value": observation.value,
            "source_ref": observation.source_ref,
        }
        for observation in series.observations
    ]


def _observation_key(identity: dict[str, Any]) -> tuple[date, float]:
    """Information identity of one observation (#139 Phase 4).

    Only (observation_date, value) is information-bearing for the capture-time
    decision set: re-capturing the same value with a later available_at is not
    a new information event, while any newly visible value for a real
    observation_date is. available_at stays recorded as capture provenance.
    """
    return (
        date.fromisoformat(str(identity["observation_date"])),
        round(float(identity["value"]), 6),
    )


def _observed_update_events(
    pack: MonitoringObservationPack,
    previous_snapshot: DashboardSnapshotV0 | None,
    registry: FactorBindingRegistry,
) -> tuple[list[ReleaseEvent], set[str]]:
    """Derive monitoring-only OBSERVED_UPDATE events (#139 Phase 4).

    The only event capture-time monitoring may truthfully assert is that a new
    observation/value became visible to this monitoring decision set, derived
    from canonical observation-identity differences between the current pack
    and the causal prior snapshot. No publication/first-release timestamp is
    invented; observation_date and available_at stay real capture-time fields.

    Fail-closed: if the causal prior snapshot does not record what was visible
    to it (e.g. a snapshot produced before this contract existed), no update is
    claimed for that series and genuine factor movement keeps raising
    SyntheticMovementError instead of being silently excused.
    """
    if previous_snapshot is None:
        return [], set()
    prior_provenance = previous_snapshot.details.get("series_provenance")
    if not isinstance(prior_provenance, dict):
        return [], set()
    series_factors: dict[str, list[str]] = {}
    for binding in registry.bindings:
        if binding.monitoring.status != "BOUND":
            continue
        for series_id in binding.canonical_series_ids:
            series_factors.setdefault(series_id, []).append(binding.factor_id)
    events: list[ReleaseEvent] = []
    for series in pack.series:
        prior_recorded = prior_provenance.get(series.series_id)
        if not isinstance(prior_recorded, dict) or not isinstance(
            prior_recorded.get("observations"), list
        ):
            continue
        prior_keys = {
            _observation_key(item)
            for item in prior_recorded["observations"]
            if isinstance(item, dict)
        }
        factors = sorted(set(series_factors.get(series.series_id, [])))
        if not factors:
            continue
        for identity in _series_observation_identities(series):
            try:
                key = _observation_key(identity)
            except (KeyError, TypeError, ValueError):
                continue
            if key in prior_keys:
                continue
            observation_date, _ = key
            captured_at = str(identity.get("available_at") or "unknown")
            for factor_id in factors:
                events.append(
                    ReleaseEvent(
                        factor_id=factor_id,
                        series_id=series.series_id,
                        event_type=ReleaseEventType.OBSERVED_UPDATE,
                        observation_date=observation_date,
                        note=(
                            "monitoring_observed_update: a new observation/value became "
                            f"visible to this monitoring decision set at {captured_at}; "
                            "capture-time semantics, no publication timestamp asserted"
                        ),
                    )
                )
    events.sort(key=lambda event: (event.series_id, event.factor_id, str(event.observation_date)))
    return events, {event.factor_id for event in events}


def build_monitoring_snapshot(
    pack: MonitoringObservationPack,
    *,
    previous_snapshot: DashboardSnapshotV0 | None = None,
    taxonomy: DecisionSupportConfig | None = None,
    registry: FactorBindingRegistry | None = None,
) -> DashboardSnapshotV0:
    """Build one truthful non-fixture DashboardSnapshotV0 in MONITORING lane."""

    _validate_pack(pack)
    economic_week_id = _economic_week_id(pack.lineage.data_cutoff)
    same_week_retry = False
    if previous_snapshot is not None:
        if previous_snapshot.metadata.decision_time >= pack.lineage.decision_time:
            raise ValueError("previous_snapshot_must_precede_current_decision_time")
        previous_week_id = _snapshot_economic_week_id(previous_snapshot)
        if previous_week_id > economic_week_id:
            raise ValueError("previous_snapshot_economic_week_after_current")
        same_week_retry = previous_week_id == economic_week_id

    taxonomy = taxonomy or load_taxonomy()
    registry = registry or load_factor_bindings(taxonomy=taxonomy)
    scores, factor_statuses = score_monitoring_factors(
        pack, taxonomy=taxonomy, registry=registry
    )
    for factor_id, score in scores.items():
        factor_statuses[factor_id]["confidence"] = score.confidence

    current_aggregates = _family_aggregates(scores, taxonomy)
    prior_scores = _previous_scores(previous_snapshot, taxonomy)
    previous_aggregates = _family_aggregates(prior_scores, taxonomy) if prior_scores else None
    clusters = _cluster_views(current_aggregates, previous_aggregates)

    growth = current_aggregates[("GROWTH_ACTIVITY", HorizonClass.CYCLICAL)]
    inflation = current_aggregates[("INFLATION_COST", HorizonClass.CYCLICAL)]
    previous_growth = (
        previous_aggregates.get(("GROWTH_ACTIVITY", HorizonClass.CYCLICAL))
        if previous_aggregates
        else None
    )
    previous_inflation = (
        previous_aggregates.get(("INFLATION_COST", HorizonClass.CYCLICAL))
        if previous_aggregates
        else None
    )
    growth_delta = (
        round(growth.score - previous_growth.score, 4)
        if growth.score is not None and previous_growth is not None and previous_growth.score is not None
        else None
    )
    inflation_delta = (
        round(inflation.score - previous_inflation.score, 4)
        if inflation.score is not None
        and previous_inflation is not None
        and previous_inflation.score is not None
        else None
    )
    macro_climate = derive_macro_climate(
        growth,
        inflation,
        growth_weekly_delta=growth_delta,
        inflation_weekly_delta=inflation_delta,
        summary="producer-owned cyclical growth/inflation climate from canonical monitoring inputs",
    )
    investment_climate = derive_investment_climate(
        current_aggregates[("FINANCIAL_CONDITIONS", HorizonClass.TACTICAL)],
        current_aggregates[("RISK_APPETITE", HorizonClass.TACTICAL)],
        current_aggregates[("MARKET_CONFIRMATION", HorizonClass.TACTICAL)],
        summary="producer-owned tactical investment climate from canonical monitoring inputs",
    )
    regime, regime_history = _build_regime(
        current_aggregates,
        previous_snapshot,
        taxonomy,
        economic_week_id=economic_week_id,
    )

    if same_week_retry and previous_snapshot is not None:
        info_delta = previous_snapshot.weekly_change.information_set_delta.model_copy(deep=True)
        macro_delta = previous_snapshot.weekly_change.macro_state_delta.model_copy(deep=True)
        market_delta = previous_snapshot.weekly_change.market_condition_delta.model_copy(deep=True)
        changed_by_release = {
            event.factor_id
            for event in info_delta.events
            if event.resolved_event_type() is not ReleaseEventType.OVERDUE
        }
    else:
        observed_events, observed_factors = _observed_update_events(
            pack, previous_snapshot, registry
        )
        info_delta = build_information_set_delta(
            [*pack.release_events, *observed_events],
            expected_releases=pack.expected_releases,
            as_of=pack.as_of,
        )
        previous_raw = (
            previous_snapshot.details.get("subfactor_scores_current", {})
            if previous_snapshot is not None
            else {}
        )
        current_raw = {
            factor_id: score.score
            for factor_id, score in scores.items()
            if score.resolved_horizon() is HorizonClass.CYCLICAL and not score.missing
        }
        previous_cyclical = {
            spec.factor_id: previous_raw[spec.factor_id]
            for spec in taxonomy.subfactors()
            if spec.resolved_horizon() is HorizonClass.CYCLICAL
            and previous_raw.get(spec.factor_id) is not None
        }
        changed_by_release = {
            event.factor_id
            for event in pack.release_events
            if event.resolved_event_type() is not ReleaseEventType.OVERDUE
        } | observed_factors
        macro_delta = build_macro_state_delta(
            previous_cyclical,
            current_raw,
            information_status=info_delta.resolved_status(),
            changed_by_release=changed_by_release,
        )
        market_delta = build_market_condition_delta(
            [
                build_market_move(
                    move.instrument,
                    move.metric_class,
                    move.prior_value,
                    move.current_value,
                    volatility_style=taxonomy.market_delta.volatility_style,
                )
                for move in pack.market_moves
            ]
        )

    gates = _asset_gates(scores, current_aggregates, taxonomy)
    asset_views, asset_delta = _asset_views_and_delta(
        gates, previous_snapshot, macro_delta.changed_factors(), taxonomy
    )
    if same_week_retry and previous_snapshot is not None:
        asset_delta = previous_snapshot.weekly_change.asset_view_delta.model_copy(deep=True)
    health = _data_health(clusters, gates, factor_statuses)

    records = registry.records(taxonomy)
    bound_count = sum(record["monitoring"]["status"] == "BOUND" for record in records)
    formal_blocked = sum(record["formal"]["status"] == "BLOCKED" for record in records)
    family_information_status: dict[str, str] = {}
    stale_factors = set(info_delta.stale_factors)
    updated_factors = changed_by_release
    for family in taxonomy.families:
        members = {spec.factor_id for spec in family.subfactors}
        if members & updated_factors:
            family_information_status[family.family_id] = InformationSetStatus.UPDATED.value
        elif members & stale_factors:
            family_information_status[family.family_id] = InformationSetStatus.OVERDUE_STALE.value
        else:
            family_information_status[family.family_id] = InformationSetStatus.NO_NEW_INFORMATION.value

    missing_count = sum(state["missing"] for state in factor_statuses.values())
    stale_count = sum(state["stale"] for state in factor_statuses.values())
    brief = ExecutiveBrief(
        what_changed=(
            f"Information set {info_delta.status.value}; "
            f"{len(changed_by_release)} factor release event(s) and {len(pack.market_moves)} market move(s)."
        ),
        why_it_matters=(
            f"MONITORING coverage is explicit: {bound_count}/{len(records)} factors bound; "
            f"{missing_count} missing and {stale_count} stale in this snapshot."
        ),
        what_to_watch=sorted(set(health.stale_components + health.missing_components))[:8],
    )

    details = {
        "producer": "REAL-SNAPSHOT-V1",
        "data_cutoff": pack.lineage.data_cutoff.isoformat(),
        "economic_week_id": economic_week_id,
        "config_identity": pack.lineage.config_identity,
        "source_mode": pack.lineage.source_mode,
        "origin": pack.origin,
        "taxonomy_version": taxonomy.version,
        "binding_registry_version": registry.version,
        "binding_counts": {
            "total_factors": len(records),
            "monitoring_bound": bound_count,
            "monitoring_unbound": len(records) - bound_count,
            "formal_blocked": formal_blocked,
            "missing": missing_count,
            "stale": stale_count,
        },
        "factor_bindings": records,
        "factor_statuses": factor_statuses,
        "subfactor_scores_current": {
            factor_id: (None if score.missing else score.score)
            for factor_id, score in sorted(scores.items())
        },
        "family_information_status": family_information_status,
        "regime_input_history": regime_history,
        "series_provenance": {
            series.series_id: {
                **series.provenance,
                "observations": _series_observation_identities(series),
            }
            for series in pack.series
        },
        "workbench_lineage": {
            "run_id": pack.lineage.run_id,
            "decision_time": pack.lineage.decision_time.isoformat(),
            "data_cutoff": pack.lineage.data_cutoff.isoformat(),
            "source_mode": pack.lineage.source_mode,
            "config_identity": pack.lineage.config_identity,
        },
    }

    return DashboardSnapshotV0(
        metadata=SnapshotMetadata(
            snapshot_id=_snapshot_id(pack, registry.version, taxonomy.version),
            as_of=pack.as_of,
            decision_time=pack.lineage.decision_time,
            lane=EvidenceLane.MONITORING,
            run_id=pack.lineage.run_id,
            model_version=MODEL_VERSION,
        ),
        macro_climate=macro_climate,
        investment_climate=investment_climate,
        climate_components=derive_climate_components(
            current_aggregates,
            previous_aggregates or current_aggregates,
            investment_climate,
        ),
        clusters=clusters,
        weekly_change=WeeklyChange(
            information_set_delta=info_delta,
            macro_state_delta=macro_delta,
            market_condition_delta=market_delta,
            asset_view_delta=asset_delta,
        ),
        regime=regime,
        asset_views=asset_views,
        cross_asset_pulse=CrossAssetPulse(
            entries=pack.pulse,
            summary="canonical monitoring pulse supplied by upstream observation pack",
        ),
        executive_brief=brief,
        data_health_summary=health,
        details=details,
    )


__all__ = [
    "MODEL_VERSION",
    "MonitoringMarketMove",
    "MonitoringObservation",
    "MonitoringObservationPack",
    "MonitoringRunLineage",
    "MonitoringSeries",
    "MonitoringSnapshotBlocked",
    "build_monitoring_snapshot",
    "score_monitoring_factors",
]