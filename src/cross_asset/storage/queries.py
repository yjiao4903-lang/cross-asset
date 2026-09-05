"""Canonical storage queries."""

from cross_asset.domain.usage import validate_usage_status

from ._time import utc_naive

_FORMAL_USAGE_STATUSES = {"RESEARCH_ADMISSIBLE", "LIVE_VERIFIED"}

# Row-quality values eligible for formal consumption. ``ok`` is a healthy
# released observation and ``closed`` is the existing healthy "source closed"
# semantic from the data-health contract. Every other value -- stale, failed,
# missing, fallback, or any unrecognized string -- fails closed and can never
# produce a formal ACTIVE allocation.
FORMAL_QUALITY_STATUSES = frozenset({"ok", "closed"})


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
    sql += ") WHERE rn=1 ORDER BY series_id, observation_date"
    return connection.execute(sql, params)


def _registry_approval_sql(alias: str) -> str:
    return f"""{alias}.status = 'PASS'
      AND {alias}.tech_gate = 'PASS'
      AND {alias}.legal_gate = 'PASS'
      AND {alias}.pit_gate = 'PASS'
      AND {alias}.stability_gate = 'PASS'
      AND {alias}.pit_grade IN ('A', 'B')
      AND {alias}.usage_status = ?
      AND {alias}.semantic_equivalence IS TRUE
      AND {alias}.origin IN ('LIVE', 'MANUAL')
      AND {alias}.source_series_id IS NOT NULL
      AND trim({alias}.source_series_id) <> ''
      AND {alias}.reviewer IS NOT NULL
      AND trim({alias}.reviewer) NOT IN ('', 'TBD')
      AND {alias}.approved_at IS NOT NULL"""


def _approved_observation_predicates(
    decision_time,
    required_usage_status,
    *,
    market_data_cutoff=None,
    series_id=None,
    allowed_quality=None,
):
    """Build the formal-consumption predicate shared by approved queries.

    Candidate observations remain stored in ``observations``. Formal consumers
    bind each row to one exact, unambiguous approved registry identity instead
    of trusting ``series_id`` alone. If multiple formal source identities are
    simultaneously approved for the same canonical series/usage, the series is
    excluded rather than silently switching or mixing sources.

    ``allowed_quality`` optionally restricts row-quality values *before* the
    latest-vintage selection so a failed or stale latest vintage can never be
    silently traded down to an older vintage by formal consumers.
    """

    usage_status = validate_usage_status(required_usage_status)
    if usage_status not in _FORMAL_USAGE_STATUSES:
        raise ValueError("formal_usage_status_required")

    # Stored available_at values are UTC-naive TIMESTAMPs; normalize the
    # decision time the same way so comparison never depends on the DuckDB
    # session timezone (a TZ-aware parameter would otherwise be cast to
    # TIMESTAMPTZ and reinterpret the naive column values).
    decision_time = utc_naive(decision_time)

    approval = _registry_approval_sql("a")
    conflict_approval = _registry_approval_sql("conflict")
    clauses = [
        "o.available_at <= ?",
        f"""EXISTS (
            SELECT 1
            FROM data_acceptance_registry a
            WHERE a.series_id = o.series_id
              AND lower(a.provider) = lower(o.source)
              AND a.source_series_id = o.source_series_id
              AND {approval}
              AND NOT EXISTS (
                  SELECT 1
                  FROM data_acceptance_registry conflict
                  WHERE conflict.series_id = a.series_id
                    AND {conflict_approval}
                    AND (
                        lower(conflict.provider) <> lower(a.provider)
                        OR conflict.source_series_id <> a.source_series_id
                    )
              )
        )""",
    ]
    params = [decision_time, usage_status, usage_status]
    if allowed_quality is not None:
        qualities = sorted(str(value).lower() for value in allowed_quality)
        if not qualities:
            raise ValueError("allowed_quality_empty")
        placeholders = ",".join("?" for _ in qualities)
        clauses.append(f"lower(o.quality) IN ({placeholders})")
        params.extend(qualities)
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
    allowed_quality=None,
):
    """Return observations from one exact approved formal source per series.

    Approval is scoped by formal ``usage_status``. This query intentionally
    does not apply freshness policy; that is a separate health gate. Row
    quality can be restricted with ``allowed_quality``.
    """

    clauses, params = _approved_observation_predicates(
        decision_time,
        required_usage_status,
        market_data_cutoff=market_data_cutoff,
        series_id=series_id,
        allowed_quality=allowed_quality,
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
    allowed_quality=None,
):
    """Return latest PIT vintages from unambiguous approved source identities."""

    clauses, params = _approved_observation_predicates(
        decision_time,
        required_usage_status,
        market_data_cutoff=market_data_cutoff,
        series_id=series_id,
        allowed_quality=allowed_quality,
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


def latest_formal_observations_asof(
    connection,
    decision_time,
    *,
    required_usage_status,
    series_ids=None,
    market_data_cutoff=None,
):
    """Single shared selection for every formal consumer (daily and research).

    This is the only sanctioned read path for formal market-data consumption.
    It binds each observation to one exact approved registry identity (the
    PR #24 contract), applies the formal row-quality gate, PIT
    ``available_at <= decision_time``, and the optional market-data cutoff,
    and returns the latest surviving vintage per series and observation date
    as a DataFrame. Formal consumers must not re-derive their own admission
    rules on top of raw ``observations``.
    """

    frame = latest_approved_observations_asof(
        connection,
        decision_time,
        required_usage_status=required_usage_status,
        market_data_cutoff=market_data_cutoff,
        allowed_quality=FORMAL_QUALITY_STATUSES,
    ).df()
    if series_ids is not None and not frame.empty:
        frame = frame[frame["series_id"].isin(set(series_ids))].copy()
    return frame.reset_index(drop=True)
