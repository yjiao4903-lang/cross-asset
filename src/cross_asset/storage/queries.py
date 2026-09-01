"""Canonical storage queries."""


def observations_asof(connection, decision_time, series_id=None):
    sql = "SELECT * FROM observations WHERE available_at <= ?"
    params = [decision_time]
    if series_id is not None:
        sql += " AND series_id = ?"
        params.append(series_id)
    return connection.execute(sql + " ORDER BY series_id, observation_date, available_at", params)


def latest_observations_asof(connection, decision_time, series_id=None):
    # Latest vintage per series and observation date, never after decision_time.
    sql = """SELECT * EXCLUDE (rn) FROM (SELECT o.*, row_number() OVER
      (PARTITION BY series_id, observation_date ORDER BY available_at DESC, ingested_at DESC) rn
      FROM observations o WHERE available_at <= ?"""
    params = [decision_time]
    if series_id is not None:
        sql += " AND series_id=?"
        params.append(series_id)
    sql += ") WHERE rn=1 ORDER BY series_id, observation_date"
    return connection.execute(sql, params)
