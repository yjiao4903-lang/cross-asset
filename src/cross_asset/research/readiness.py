"""Read-only readiness checks for formal real-data OOS research."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from cross_asset.storage import approved_observations_asof

from .protocol import ResearchProtocol


def _columns(connection, table: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    }


def _required_series(connection) -> list[str]:
    if not _columns(connection, "series_catalog"):
        return []
    rows = connection.execute(
        """SELECT series_id FROM series_catalog
           WHERE active=TRUE AND critical=TRUE ORDER BY series_id"""
    ).fetchall()
    return [row[0] for row in rows]


def _decision_times(values) -> pd.DatetimeIndex:
    if values is None:
        return pd.DatetimeIndex([])
    parsed = pd.DatetimeIndex(pd.to_datetime(list(values), utc=True))
    if parsed.has_duplicates or not parsed.is_monotonic_increasing:
        raise ValueError("decision_times_must_be_strictly_increasing_and_unique")
    return parsed


def _series_freshness_hours(connection, series_id: str) -> float | None:
    row = connection.execute(
        "SELECT stale_after_hours FROM series_catalog WHERE series_id=?",
        [series_id],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    value = float(row[0])
    return value if value > 0 else None


def _accepted_registry_rows(
    connection,
    series_id: str,
    protocol: ResearchProtocol,
):
    return connection.execute(
        """SELECT status,usage_status,pit_grade,reviewer,approved_at,provider,source_series_id
           FROM data_acceptance_registry
           WHERE series_id=?
             AND status=?
             AND usage_status=?
             AND tech_gate='PASS'
             AND legal_gate='PASS'
             AND pit_gate='PASS'
             AND stability_gate='PASS'
             AND pit_grade IN ('A','B')
             AND semantic_equivalence IS TRUE
             AND origin IN ('LIVE','MANUAL')
             AND source_series_id IS NOT NULL
             AND trim(source_series_id) <> ''
             AND reviewer IS NOT NULL
             AND trim(reviewer) NOT IN ('','TBD')
             AND approved_at IS NOT NULL
           ORDER BY provider,source_series_id""",
        [
            series_id,
            protocol.required_registry_status,
            protocol.required_usage_status,
        ],
    ).fetchall()


def _pit_coverage(
    connection,
    series_id: str,
    decision_times: pd.DatetimeIndex,
    approved_observations: pd.DataFrame,
) -> dict:
    """Measure PIT coverage using only formally approved source observations."""

    stale_after_hours = _series_freshness_hours(connection, series_id)
    if len(decision_times) == 0:
        return {
            "eligible_decisions": 0,
            "covered_decisions": 0,
            "coverage": None,
            "stale_after_hours": stale_after_hours,
        }

    rows = approved_observations[
        approved_observations["series_id"] == series_id
    ]
    available = pd.DatetimeIndex(
        pd.to_datetime(rows["available_at"].tolist(), utc=True)
    )
    available = available.sort_values()
    covered = 0
    for decision in decision_times:
        position = int(available.searchsorted(decision, side="right")) - 1
        if position < 0:
            continue
        latest = available[position]
        if stale_after_hours is not None:
            age_hours = (decision - latest).total_seconds() / 3600.0
            if age_hours > stale_after_hours:
                continue
        covered += 1
    total = len(decision_times)
    return {
        "eligible_decisions": total,
        "covered_decisions": covered,
        "coverage": covered / total if total else None,
        "stale_after_hours": stale_after_hours,
    }


def evaluate_research_readiness(
    connection,
    protocol: ResearchProtocol,
    *,
    required_series: list[str] | tuple[str, ...] | None = None,
    decision_times=None,
) -> dict:
    """Evaluate protocol, approved observations, history and PIT coverage."""

    catalog_critical = _required_series(connection)
    required = sorted(set(catalog_critical) | set(required_series or ()))
    research_decisions = _decision_times(decision_times)
    blockers = list(protocol.execution_blockers)

    readiness_asof = (
        research_decisions[-1].to_pydatetime()
        if len(research_decisions)
        else datetime.now(UTC)
    )
    approved = approved_observations_asof(
        connection,
        readiness_asof,
        required_usage_status=protocol.required_usage_status,
    ).df()
    formal_count = int(len(approved))
    if formal_count == 0:
        blockers.append("formal_observations_empty")
    if not required:
        blockers.append("critical_series_not_declared")

    series = []
    ready_count = 0
    coverage_ready_count = 0
    for series_id in required:
        registry = _accepted_registry_rows(connection, series_id, protocol)
        identities = {
            (str(row[5]).lower(), str(row[6]))
            for row in registry
        }
        registry_ready = len(identities) == 1
        selected_registry = registry[0] if registry_ready else None

        rows = approved[approved["series_id"] == series_id].copy()
        count = int(len(rows))
        if count:
            start = rows["observation_date"].min()
            end = rows["observation_date"].max()
            max_available = rows["available_at"].max()
            history_years = (
                pd.Timestamp(end) - pd.Timestamp(start)
            ).days / 365.25
        else:
            start = end = max_available = None
            history_years = 0.0

        coverage = _pit_coverage(
            connection,
            series_id,
            research_decisions,
            approved,
        )
        item_blockers = []
        if not registry:
            item_blockers.append("registry_pass_research_admissible_required")
        elif not registry_ready:
            item_blockers.append("formal_source_identity_ambiguous")
        if count == 0:
            item_blockers.append("formal_observations_missing")
        elif history_years < protocol.train_min_years:
            item_blockers.append("history_shorter_than_train_min_years")
        if coverage["coverage"] is not None:
            if float(coverage["coverage"]) < protocol.coverage_threshold:
                item_blockers.append("pit_coverage_below_threshold")
            else:
                coverage_ready_count += 1
        elif len(research_decisions):
            item_blockers.append("pit_coverage_unavailable")

        if not item_blockers:
            ready_count += 1
        series.append(
            {
                "series_id": series_id,
                "registry_ready": registry_ready,
                "pit_grade": selected_registry[2] if selected_registry else None,
                "provider": selected_registry[5] if selected_registry else None,
                "source_series_id": selected_registry[6] if selected_registry else None,
                "observation_count": count,
                "history_start": start,
                "history_end": end,
                "history_years": history_years,
                "max_available_at": max_available,
                "pit_coverage": coverage,
                "blockers": item_blockers,
            }
        )
        blockers.extend(f"{series_id}:{reason}" for reason in item_blockers)

    critical_ready_fraction = ready_count / len(required) if required else 0.0
    coverage_ready_fraction = (
        coverage_ready_count / len(required)
        if required and len(research_decisions)
        else None
    )
    if protocol.require_all_critical_series and ready_count != len(required):
        blockers.append("not_all_critical_series_ready")

    blockers = sorted(set(blockers))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "READY_FOR_OOS" if not blockers else "BLOCKED",
        "protocol_hash": protocol.protocol_hash,
        "protocol_status": protocol.status,
        "project_status": protocol.project_status,
        "coverage_threshold": protocol.coverage_threshold,
        "decision_time_count": len(research_decisions),
        "formal_observation_count": formal_count,
        "critical_series_count": len(required),
        "critical_series_ready": ready_count,
        "critical_ready_fraction": critical_ready_fraction,
        "coverage_series_ready_fraction": coverage_ready_fraction,
        "series": series,
        "blockers": blockers,
    }


__all__ = ["evaluate_research_readiness"]
