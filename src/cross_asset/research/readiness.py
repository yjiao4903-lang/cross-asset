"""Read-only readiness checks for formal real-data OOS research."""

from __future__ import annotations

from datetime import UTC, datetime

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


def evaluate_research_readiness(
    connection,
    protocol: ResearchProtocol,
    *,
    required_series: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Evaluate protocol, registry, formal observations and history without mutating state."""

    required = list(required_series) if required_series is not None else _required_series(connection)
    blockers = list(protocol.execution_blockers)
    formal_count = int(connection.execute("SELECT count(*) FROM observations").fetchone()[0])
    if formal_count == 0:
        blockers.append("formal_observations_empty")
    if not required:
        blockers.append("critical_series_not_declared")

    series = []
    ready_count = 0
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
        item_blockers = []
        if not accepted:
            item_blockers.append("registry_pass_research_admissible_required")
        if count == 0:
            item_blockers.append("formal_observations_missing")
        elif history_years < protocol.train_min_years:
            item_blockers.append("history_shorter_than_train_min_years")
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
                "blockers": item_blockers,
            }
        )
        blockers.extend(f"{series_id}:{reason}" for reason in item_blockers)

    critical_ready_fraction = ready_count / len(required) if required else 0.0
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
        "formal_observation_count": formal_count,
        "critical_series_count": len(required),
        "critical_series_ready": ready_count,
        "critical_ready_fraction": critical_ready_fraction,
        "series": series,
        "blockers": blockers,
    }


__all__ = ["evaluate_research_readiness"]
