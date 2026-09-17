"""Configuration-backed activation and read-model for the existing series catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from ._time import utc_naive


def _load_yaml(path: str | Path) -> dict:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def sync_series_catalog(
    store,
    *,
    series_ids=None,
    provider=None,
    series_config: str | Path = "config/series.yml",
    sources_config: str | Path = "config/sources.yml",
    now=None,
) -> dict:
    """Seed existing catalog/mapping tables from configuration without admission.

    This function never writes ``data_acceptance_registry``. Provider mappings
    are operational identities only; formal eligibility remains governed by the
    separate acceptance registry and sanctioned formal queries.
    """

    wanted = set(series_ids or [])
    now = utc_naive(now or datetime.now(UTC))
    series_payload = _load_yaml(series_config)
    sources_payload = _load_yaml(sources_config)

    series_rows = []
    for item in series_payload.get("series", []) or []:
        if not isinstance(item, dict) or not item.get("series_id"):
            continue
        sid = str(item["series_id"])
        if wanted and sid not in wanted:
            continue
        current = store.conn.execute(
            """SELECT asset_class,category,timezone,point_in_time_class,created_at
               FROM series_catalog WHERE series_id=?""",
            [sid],
        ).fetchone()
        asset_class = item.get("asset_class") or (current[0] if current else None)
        category = item.get("category") or (current[1] if current else None)
        timezone = item.get("timezone") or (current[2] if current else None)
        pit_class = item.get("point_in_time_class") or (
            current[3] if current else "UNCLASSIFIED"
        )
        created_at = current[4] if current else now
        row = [
            sid,
            str(item.get("display_name") or sid),
            asset_class,
            category,
            str(item.get("frequency") or "unknown"),
            str(item.get("unit") or "unknown"),
            item.get("currency"),
            timezone,
            bool(item.get("critical", False)),
            str(pit_class),
            item.get("stale_after_hours"),
            bool(item.get("active", True)),
            created_at,
            now,
        ]
        store.conn.execute(
            """INSERT INTO series_catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(series_id) DO UPDATE SET
                 display_name=excluded.display_name,
                 asset_class=excluded.asset_class,
                 category=excluded.category,
                 frequency=excluded.frequency,
                 unit=excluded.unit,
                 currency=excluded.currency,
                 timezone=excluded.timezone,
                 critical=excluded.critical,
                 point_in_time_class=excluded.point_in_time_class,
                 stale_after_hours=excluded.stale_after_hours,
                 active=excluded.active,
                 updated_at=excluded.updated_at""",
            row,
        )
        series_rows.append(sid)

    mapping_rows = []
    for item in sources_payload.get("mappings", []) or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("series_id") or "")
        mapping_provider = str(item.get("provider") or "")
        source_series_id = str(item.get("source_series_id") or "")
        if not sid or not mapping_provider or not source_series_id:
            continue
        if wanted and sid not in wanted:
            continue
        if provider and mapping_provider.lower() != str(provider).lower():
            continue
        store.conn.execute(
            """INSERT INTO source_mapping
               (series_id,provider,source_series_id,priority,enabled,
                semantic_equivalence,adjustment,notes)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(series_id,provider,source_series_id) DO UPDATE SET
                 priority=excluded.priority,
                 enabled=excluded.enabled,
                 semantic_equivalence=excluded.semantic_equivalence,
                 adjustment=excluded.adjustment,
                 notes=excluded.notes""",
            [
                sid,
                mapping_provider,
                source_series_id,
                int(item.get("priority", 999)),
                bool(item.get("enabled", True)),
                bool(item.get("semantic_equivalence", True)),
                item.get("adjustment"),
                item.get("notes"),
            ],
        )
        mapping_rows.append((sid, mapping_provider, source_series_id))

    return {
        "series_catalog_rows": len(series_rows),
        "source_mapping_rows": len(mapping_rows),
        "acceptance_registry_writes": 0,
    }


def expected_source_identities(conn, provider: str, series_ids) -> dict[str, set[str]]:
    """Return enabled configured identities for a monitoring provider."""

    result = {str(series_id): set() for series_id in series_ids}
    if not result:
        return result
    placeholders = ",".join("?" for _ in result)
    rows = conn.execute(
        f"""SELECT series_id,source_series_id
            FROM source_mapping
            WHERE lower(provider)=lower(?) AND enabled=TRUE
              AND series_id IN ({placeholders})""",
        [provider, *result],
    ).fetchall()
    for sid, source_series_id in rows:
        result.setdefault(str(sid), set()).add(str(source_series_id))
    return result


def update_catalog_from_monitoring_rows(store, rows) -> None:
    """Fill only missing operational metadata from observed monitoring rows."""

    for row in rows:
        sid = str(row.get("series_id") or "")
        if not sid:
            continue
        current = store.conn.execute(
            "SELECT frequency,unit,currency,timezone FROM series_catalog WHERE series_id=?",
            [sid],
        ).fetchone()
        if current is None:
            continue
        values = {
            "frequency": current[0] or row.get("frequency"),
            "unit": current[1] or row.get("unit"),
            "currency": current[2] or row.get("currency"),
            "timezone": current[3] or row.get("timezone"),
        }
        store.conn.execute(
            """UPDATE series_catalog
               SET frequency=?,unit=?,currency=?,timezone=?,updated_at=?
               WHERE series_id=?""",
            [
                values["frequency"],
                values["unit"],
                values["currency"],
                values["timezone"],
                utc_naive(datetime.now(UTC)),
                sid,
            ],
        )


def series_catalog_read_model(conn, *, series_ids=None, provider=None) -> list[dict]:
    """Expose catalog + operational provider identity + explicit usage separation."""

    clauses = ["c.active=TRUE"]
    params = []
    if series_ids:
        ids = [str(value) for value in series_ids]
        clauses.append("c.series_id IN (" + ",".join("?" for _ in ids) + ")")
        params.extend(ids)
    if provider:
        clauses.append("lower(m.provider)=lower(?)")
        params.append(str(provider))
    sql = f"""SELECT c.*,m.provider,m.source_series_id,m.priority,m.enabled AS mapping_enabled,
                     m.semantic_equivalence,m.notes AS mapping_notes
              FROM series_catalog c
              LEFT JOIN source_mapping m ON m.series_id=c.series_id
              WHERE {' AND '.join(clauses)}
              ORDER BY c.series_id,m.priority,m.provider,m.source_series_id"""
    rows = _rows(conn, sql, params)
    for row in rows:
        registry = []
        if row.get("provider") and row.get("source_series_id"):
            registry = _rows(
                conn,
                """SELECT usage_status,status,pit_grade,origin
                   FROM data_acceptance_registry
                   WHERE series_id=? AND lower(provider)=lower(?)
                     AND source_series_id=?
                   ORDER BY usage_status""",
                [row["series_id"], row["provider"], row["source_series_id"]],
            )
        row["usage_eligibility"] = (
            "MONITORING_WITH_REGISTRY_RECORD" if registry else "MONITORING_ONLY"
        )
        row["registry_usage_statuses"] = sorted(
            {str(item["usage_status"]) for item in registry}
        )
        row["freshness_expectation"] = {
            "stale_after_hours": row.get("stale_after_hours")
        }
    return rows


__all__ = [
    "expected_source_identities",
    "series_catalog_read_model",
    "sync_series_catalog",
    "update_catalog_from_monitoring_rows",
]
