"""DECISION-HISTORY-V1 read model over persisted DashboardSnapshotV0 files.

The merged snapshot remains the authority. This module does not create a second
state engine; it derives canonical economic-week history, stance trajectories
and structured diffs from persisted snapshots.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from .snapshot import DashboardSnapshotV0

HISTORY_CONTRACT = "DECISION-HISTORY-V1"
YTD_STATUS = "DEFERRED"


def economic_week_id(value: date) -> str:
    """Stable economic-week identity: Monday date for the decision/data week."""

    return (value - timedelta(days=value.weekday())).isoformat()


def snapshot_economic_week_id(snapshot: DashboardSnapshotV0) -> str:
    explicit = snapshot.details.get("economic_week_id")
    if explicit:
        return str(explicit)
    cutoff = snapshot.details.get("data_cutoff")
    if cutoff:
        try:
            return economic_week_id(date.fromisoformat(str(cutoff)[:10]))
        except ValueError:
            pass
    return economic_week_id(snapshot.metadata.as_of)


def technical_sort_key(snapshot: DashboardSnapshotV0) -> tuple[datetime, str]:
    return snapshot.metadata.decision_time, snapshot.metadata.snapshot_id


def canonical_by_week(
    snapshots: Iterable[DashboardSnapshotV0],
) -> list[DashboardSnapshotV0]:
    """Choose one deterministic canonical technical snapshot per economic week.

    Same-week retries are one economic step. The canonical representative is
    the latest decision_time in that week, with snapshot_id as deterministic
    tie-break. Superseded technical snapshots remain persisted and queryable.
    """

    grouped: dict[str, list[DashboardSnapshotV0]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot_economic_week_id(snapshot)].append(snapshot)
    selected = [max(entries, key=technical_sort_key) for entries in grouped.values()]
    return sorted(
        selected,
        key=lambda snapshot: (snapshot_economic_week_id(snapshot), *technical_sort_key(snapshot)),
    )


def canonical_prior(
    snapshots: Iterable[DashboardSnapshotV0],
    *,
    decision_time: datetime,
    current_week_id: str,
) -> DashboardSnapshotV0 | None:
    """Return the latest canonical earlier economic week without look-ahead."""

    eligible = [
        snapshot
        for snapshot in canonical_by_week(snapshots)
        if snapshot.metadata.decision_time < decision_time
        and snapshot_economic_week_id(snapshot) < current_week_id
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda snapshot: (snapshot_economic_week_id(snapshot), *technical_sort_key(snapshot)),
    )


def _asset_key(asset: Any) -> str:
    return str(getattr(asset, "value", asset))


def snapshot_summary(
    snapshot: DashboardSnapshotV0,
    *,
    canonical: bool,
    superseded_snapshot_ids: list[str] | None = None,
) -> dict[str, Any]:
    lineage = dict(snapshot.details.get("workbench_lineage", {}))
    return {
        "snapshot_id": snapshot.metadata.snapshot_id,
        "economic_week_id": snapshot_economic_week_id(snapshot),
        "as_of": snapshot.metadata.as_of.isoformat(),
        "decision_time": snapshot.metadata.decision_time.isoformat(),
        "data_cutoff": str(snapshot.details.get("data_cutoff", lineage.get("data_cutoff", ""))),
        "run_id": snapshot.metadata.run_id,
        "workbench_lineage": lineage,
        "snapshot_version": snapshot.metadata.snapshot_version,
        "model_version": snapshot.metadata.model_version,
        "config_identity": snapshot.details.get("config_identity", lineage.get("config_identity")),
        "taxonomy_version": snapshot.details.get("taxonomy_version"),
        "binding_registry_version": snapshot.details.get("binding_registry_version"),
        "lane": str(getattr(snapshot.metadata.lane, "value", snapshot.metadata.lane)),
        "regime": snapshot.regime.model_dump(mode="json"),
        "factor_states": dict(snapshot.details.get("subfactor_scores_current", {})),
        "factor_statuses": dict(snapshot.details.get("factor_statuses", {})),
        "clusters": [cluster.model_dump(mode="json") for cluster in snapshot.clusters],
        "asset_views": [view.model_dump(mode="json") for view in snapshot.asset_views],
        "data_health": snapshot.data_health_summary.model_dump(mode="json"),
        "canonical_economic_week": canonical,
        "superseded_snapshot_ids": superseded_snapshot_ids or [],
        "ytd": {"status": YTD_STATUS, "reason": "return/FX/accounting contract not authorized"},
    }


def history_payload(
    snapshots: Iterable[DashboardSnapshotV0],
    *,
    start_week: str | None = None,
    end_week: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    technical = sorted(list(snapshots), key=lambda s: (snapshot_economic_week_id(s), *technical_sort_key(s)))
    canonical = canonical_by_week(technical)
    if start_week is not None:
        canonical = [s for s in canonical if snapshot_economic_week_id(s) >= start_week]
    if end_week is not None:
        canonical = [s for s in canonical if snapshot_economic_week_id(s) <= end_week]
    if limit is not None:
        if limit < 1:
            raise ValueError("history_limit_must_be_positive")
        canonical = canonical[-limit:]

    technical_by_week: dict[str, list[DashboardSnapshotV0]] = defaultdict(list)
    for snapshot in technical:
        technical_by_week[snapshot_economic_week_id(snapshot)].append(snapshot)

    entries = []
    for snapshot in canonical:
        week_id = snapshot_economic_week_id(snapshot)
        superseded = [
            candidate.metadata.snapshot_id
            for candidate in technical_by_week[week_id]
            if candidate.metadata.snapshot_id != snapshot.metadata.snapshot_id
        ]
        entries.append(snapshot_summary(snapshot, canonical=True, superseded_snapshot_ids=superseded))

    current = entries[-1] if entries else None
    prior = entries[-2] if len(entries) >= 2 else None
    return {
        "contract": HISTORY_CONTRACT,
        "view": "CANONICAL_ECONOMIC_WEEK",
        "current": current,
        "prior": prior,
        "history": entries,
        "technical_snapshot_count": len(technical),
        "canonical_week_count": len(entries),
        "ytd": {"status": YTD_STATUS},
    }


def technical_history_payload(snapshots: Iterable[DashboardSnapshotV0]) -> dict[str, Any]:
    technical = sorted(list(snapshots), key=lambda s: (snapshot_economic_week_id(s), *technical_sort_key(s)))
    canonical_ids = {s.metadata.snapshot_id for s in canonical_by_week(technical)}
    return {
        "contract": HISTORY_CONTRACT,
        "view": "TECHNICAL_SNAPSHOTS",
        "history": [
            snapshot_summary(snapshot, canonical=snapshot.metadata.snapshot_id in canonical_ids)
            for snapshot in technical
        ],
        "technical_snapshot_count": len(technical),
        "canonical_week_count": len(canonical_ids),
        "ytd": {"status": YTD_STATUS},
    }


def asset_stance_history(
    snapshots: Iterable[DashboardSnapshotV0],
    asset: str,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for snapshot in canonical_by_week(snapshots):
        view = next((v for v in snapshot.asset_views if _asset_key(v.asset) == asset), None)
        if view is None:
            continue
        entries.append(
            {
                "snapshot_id": snapshot.metadata.snapshot_id,
                "economic_week_id": snapshot_economic_week_id(snapshot),
                "decision_time": snapshot.metadata.decision_time.isoformat(),
                "run_id": snapshot.metadata.run_id,
                "stance": view.stance,
                "prior_stance": view.prior_stance,
                "confidence": view.confidence,
                "macro_bias": view.macro_bias,
                "market_confirmation": str(
                    getattr(view.market_confirmation, "value", view.market_confirmation)
                ),
                "drivers": list(view.drivers),
                "counter_signals": list(view.counter_signals),
                "invalidator": view.invalidator,
                "data_health": str(getattr(view.data_health, "value", view.data_health)),
            }
        )
    if not entries:
        raise KeyError(f"asset_history_not_found:{asset}")
    return {
        "contract": HISTORY_CONTRACT,
        "asset": asset,
        "trajectory": entries,
        "ytd": {"status": YTD_STATUS},
    }


def _changed_map(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, dict[str, Any]]:
    changed: dict[str, dict[str, Any]] = {}
    for key in sorted(set(previous) | set(current)):
        before = previous.get(key)
        after = current.get(key)
        if before != after:
            changed[key] = {"prior": before, "current": after}
    return changed


def structured_diff(current: DashboardSnapshotV0, prior: DashboardSnapshotV0) -> dict[str, Any]:
    if prior.metadata.decision_time > current.metadata.decision_time:
        raise ValueError("diff_prior_is_future")

    current_clusters = {cluster.cluster_id: cluster.model_dump(mode="json") for cluster in current.clusters}
    prior_clusters = {cluster.cluster_id: cluster.model_dump(mode="json") for cluster in prior.clusters}
    current_assets = {_asset_key(view.asset): view.model_dump(mode="json") for view in current.asset_views}
    prior_assets = {_asset_key(view.asset): view.model_dump(mode="json") for view in prior.asset_views}
    current_health = current.data_health_summary.model_dump(mode="json")
    prior_health = prior.data_health_summary.model_dump(mode="json")

    factor_changes = _changed_map(
        dict(prior.details.get("subfactor_scores_current", {})),
        dict(current.details.get("subfactor_scores_current", {})),
    )
    factor_status_changes = _changed_map(
        dict(prior.details.get("factor_statuses", {})),
        dict(current.details.get("factor_statuses", {})),
    )
    cluster_changes = _changed_map(prior_clusters, current_clusters)
    asset_changes = _changed_map(prior_assets, current_assets)
    regime_before = prior.regime.model_dump(mode="json")
    regime_after = current.regime.model_dump(mode="json")
    regime_change = None if regime_before == regime_after else {"prior": regime_before, "current": regime_after}
    health_change = None if prior_health == current_health else {"prior": prior_health, "current": current_health}

    return {
        "contract": HISTORY_CONTRACT,
        "current": snapshot_summary(current, canonical=True),
        "prior": snapshot_summary(prior, canonical=True),
        "same_economic_week": snapshot_economic_week_id(current) == snapshot_economic_week_id(prior),
        "changes": {
            "factor_states": factor_changes,
            "factor_statuses": factor_status_changes,
            "clusters": cluster_changes,
            "regime": regime_change,
            "asset_views": asset_changes,
            "data_health": health_change,
        },
        "has_state_changes": any(
            [factor_changes, factor_status_changes, cluster_changes, regime_change, asset_changes, health_change]
        ),
        "evidence": {
            "current_snapshot_id": current.metadata.snapshot_id,
            "current_run_id": current.metadata.run_id,
            "prior_snapshot_id": prior.metadata.snapshot_id,
            "prior_run_id": prior.metadata.run_id,
            "current_series_provenance": current.details.get("series_provenance", {}),
            "prior_series_provenance": prior.details.get("series_provenance", {}),
        },
        "ytd": {"status": YTD_STATUS},
    }


__all__ = [
    "HISTORY_CONTRACT",
    "YTD_STATUS",
    "asset_stance_history",
    "canonical_by_week",
    "canonical_prior",
    "economic_week_id",
    "history_payload",
    "snapshot_economic_week_id",
    "structured_diff",
    "technical_history_payload",
]
