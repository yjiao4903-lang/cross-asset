"""Read-only readiness checks for formal real-data OOS research."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

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


def _pit_coverage(
    connection,
    series_id: str,
    decision_times: pd.DatetimeIndex,
) -> dict:
    """Measure usable PIT coverage over explicit research decision times.

    A decision is covered when at least one observation was available by the
    decision time. When stale_after_hours is declared in the series catalog,
    the most recent PIT observation must also remain fresh at that decision.
    """

    stale_after_hours = _series_freshness_hours(connection, series_id)
    if len(decision_times) == 0:
        return {
            "eligible_decisions": 0,
            "covered_decisions": 0,
            "coverage": None,
            "stale_after_hours": stale_after_hours,
        }

    rows = connection.execute(
        """SELECT available_at FROM observations
           WHERE series_id=? ORDER BY available_at""",
        [series_id],
    ).fetchall()
    available = pd.DatetimeIndex(
        pd.to_datetime([row[0] for row in rows], utc=True)
    )
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
    """Evaluate protocol, registry, formal observations, history and PIT coverage."""

    catalog_critical = _required_series(connection)
    required = sorted(
        set(catalog_critical)
        | set(required_series or ())
    )
    research_decisions = _decision_times(decision_times)
    blockers = list(protocol.execution_blockers)
    formal_count = int(
        connection.execute("SELECT count(*) FROM observations").fetchone()[0]
    )
    if formal_count == 0:
        blockers.append("formal_observations_empty")
    if not required:
        blockers.append("critical_series_not_declared")

    series = []
    ready_count = 0
    coverage_ready_count = 0
    for series_id in required:
        registry = connection.execute(
            """SELECT status,usage_status,pit_grade,reviewer,approved_at,provider,source_series_id
               FROM data_acceptance_registry
               WHERE series_id=?
               ORDER BY updated_at DESC""",
            [series_id],
        ).fetchall()
        accepted = [
            row
            for row in registry
            if row[0] == protocol.required_registry_status
            and row[1] == protocol.required_usage_status
            and row[3] not in (None, "", "TBD")
            and row[4] is not None
        ]
        stats = connection.execute(
            """SELECT count(*),min(observation_date),max(observation_date),max(available_at)
               FROM observations WHERE series_id=?""",
            [series_id],
        ).fetchone()
        count = int(stats[0])
        start, end, max_available = stats[1], stats[2], stats[3]
        history_years = (
            (end - start).days / 365.25
            if count and start is not None and end is not None
            else 0.0
        )
        coverage = _pit_coverage(connection, series_id, research_decisions)
        item_blockers = []
        if not accepted:
            item_blockers.append("registry_pass_research_admissible_required")
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
                "registry_ready": bool(accepted),
                "pit_grade": accepted[0][2] if accepted else None,
                "provider": accepted[0][5] if accepted else None,
                "source_series_id": accepted[0][6] if accepted else None,
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
