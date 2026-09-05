"""Canonical storage queries."""

from cross_asset.domain.usage import validate_usage_status


def observations_asof(
    connection,
    decision_time,
    series_id=None,
    *,
    market_data_cutoff=None,
):
    sql = "SELECT * FROM observations WHERE available_at <= ?"
    params = [decision_time]
    if market_data_cutoff is not None:
        sql += " AND observation_date <= ?"
        params.append(market_data_cutoff)
    if series_id is not None:
        sql += " AND series_id = ?"
        params.append(series_id)
    return connection.execute(
        sql + " ORDER BY series_id, observation_date, available_at",
        params,
    )


def latest_observations_asof(
    connection,
    decision_time,
    series_id=None,
    *,
    market_data_cutoff=None,
):
    # Latest vintage per series and observation date, never after decision_time.
    sql = """SELECT * EXCLUDE (rn) FROM (SELECT o.*, row_number() OVER
      (PARTITION BY series_id, observation_date ORDER BY available_at DESC, ingested_at DESC) rn
      FROM observations o WHERE available_at <= ?"""
    params = [decision_time]
    if market_data_cutoff is not None:
        sql += " AND observation_date <= ?"
        params.append(market_data_cutoff)
    if series_id is not None:
        sql += " AND series_id=?"
        params.append(series_id)
    sql += ") WHERE rn=1 ORDER BY series_id, observation_date, available_at"
    return connection.execute(sql, params)


def _approved_observation_predicates(
    decision_time,
    required_usage_status,
    *,
    market_data_cutoff=None,
    series_id=None,
):
    """Build the formal-consumption predicate shared by approved queries.

    Candidate observations remain stored in ``observations``. Formal consumers
    must bind each row to the exact approved registry identity instead of
    trusting ``series_id`` alone.
    """

    usage_status = validate_usage_status(required_usage_status)
    clauses = [
        "o.available_at <= ?",
        """EXISTS (
            SELECT 1
            FROM data_acceptance_registry a
            WHERE a.series_id = o.series_id
              AND lower(a.provider) = lower(o.source)
              AND a.source_series_id = o.source_series_id
              AND a.status = 'PASS'
              AND a.tech_gate = 'PASS'
              AND a.legal_gate = 'PASS'
              AND a.pit_gate = 'PASS'
              AND a.stability_gate = 'PASS'
              AND a.pit_grade IN ('A', 'B')
              AND a.usage_status = ?
              AND a.semantic_equivalence IS TRUE
              AND a.reviewer IS NOT NULL
              AND trim(a.reviewer) NOT IN ('', 'TBD')
              AND a.approved_at IS NOT NULL
        )""",
    ]
    params = [decision_time, usage_status]
    if market_data_cutoff is not None:
        clauses.append("o.observation_date <= ?")
        params.append(market_data_cutoff)
    if series_id is not None:
        clauses.append("o.series_id = ?")
        params.append(series_id)
    return clauses, params


def approved_observations_asof(
    connection,
    decision_time,
    *,
    required_usage_status,
    series_id=None,
    market_data_cutoff=None,
):
    """Return only observations whose exact source identity is approved.

    Approval is scoped by ``usage_status``. This query intentionally does not
    apply freshness or row-quality policy; those are separate health gates.
    """

    clauses, params = _approved_observation_predicates(
        decision_time,
        required_usage_status,
        market_data_cutoff=market_data_cutoff,
        series_id=series_id,
    )
    sql = "SELECT o.* FROM observations o WHERE " + " AND ".join(clauses)
    sql += " ORDER BY o.series_id, o.observation_date, o.available_at"
    return connection.execute(sql, params)


def latest_approved_observations_asof(
    connection,
    decision_time,
    *,
    required_usage_status,
    series_id=None,
    market_data_cutoff=None,
):
    """Return latest PIT vintages from the exact approved source identities."""

    clauses, params = _approved_observation_predicates(
        decision_time,
        required_usage_status,
        market_data_cutoff=market_data_cutoff,
        series_id=series_id,
    )
    sql = """SELECT * EXCLUDE (rn) FROM (
        SELECT o.*, row_number() OVER (
            PARTITION BY o.series_id, o.observation_date
            ORDER BY o.available_at DESC, o.ingested_at DESC
        ) rn
        FROM observations o
        WHERE """ + " AND ".join(clauses)
    sql += ") WHERE rn=1 ORDER BY series_id, observation_date, available_at"
    return connection.execute(sql, params)
