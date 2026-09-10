"""Small transactional DuckDB repository."""

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from ._time import utc_naive
from .schema import initialize_schema


class DuckDBStore:
    def __init__(self, path=":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(self.path)
        initialize_schema(self.connection)

    @property
    def conn(self):
        return self.connection

    def close(self):
        self.connection.close()

    def transaction(self):
        return self.connection

    @contextmanager
    def atomic(self):
        self.connection.execute("BEGIN")
        try:
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    run_transaction = atomic

    def start_run(self, provider, run_id, requested_series=None, started_at=None):
        started_at = utc_naive(started_at or datetime.now(UTC).replace(tzinfo=None))
        self.connection.execute(
            "INSERT INTO ingestion_runs(run_id,provider,started_at,status,requested_series) VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            [str(run_id), provider, started_at, "running", requested_series],
        )

    def finish_run(self, run_id, status, **fields):
        allowed = {
            "finished_at",
            "success_series",
            "failed_series",
            "rows_written",
            "error_summary",
        }
        fields = {k: v for k, v in fields.items() if k in allowed}
        fields["finished_at"] = utc_naive(
            fields.get("finished_at", datetime.now(UTC).replace(tzinfo=None))
        )
        fields["status"] = status
        assignments = ", ".join(f"{k}=?" for k in fields)
        self.connection.execute(
            f"UPDATE ingestion_runs SET {assignments} WHERE run_id=?",
            [*fields.values(), str(run_id)],
        )

    def insert_observations(self, rows, run_id=None):
        """Insert observations idempotently; returns number newly inserted.

        Bulk multi-row insert (semantics identical to the previous per-row
        SELECT+INSERT: unique-key conflicts are skipped, return value is the
        number of rows newly present) to avoid O(n) per-row scans.
        """
        if not rows:
            return 0
        prepared = []
        for row in rows:
            r = dict(row)
            r["run_id"] = str(run_id or r.get("run_id", ""))
            r["available_at"] = utc_naive(r.get("available_at"))
            r["ingested_at"] = utc_naive(r.get("ingested_at"))
            prepared.append(r)
        cols = [
            "series_id",
            "observation_date",
            "available_at",
            "value",
            "source",
            "source_series_id",
            "vintage_date",
            "ingested_at",
            "quality",
            "raw_file",
            "run_id",
        ]
        before = self.connection.execute("SELECT count(*) FROM observations").fetchone()[0]
        self.connection.execute("BEGIN")
        try:
            for start in range(0, len(prepared), 1000):
                chunk = prepared[start : start + 1000]
                placeholders = ",".join(
                    "(" + ",".join("?" for _ in cols) + ")" for _ in chunk
                )
                flat = [r.get(c) for r in chunk for c in cols]
                self.connection.execute(
                    f"INSERT INTO observations VALUES {placeholders} "
                    "ON CONFLICT DO NOTHING",
                    flat,
                )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        after = self.connection.execute("SELECT count(*) FROM observations").fetchone()[0]
        return int(after - before)

    def query(self, sql, params=None):
        return self.connection.execute(sql, params or [])

    def record_quality_event(self, event):
        r = dict(event)
        cols = [
            "event_id",
            "detected_at",
            "series_id",
            "severity",
            "event_type",
            "message",
            "provider",
            "run_id",
        ]
        r["detected_at"] = utc_naive(r.get("detected_at"))
        self.connection.execute(
            "INSERT INTO data_quality_events VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            [r.get(c) for c in cols],
        )

    def record_provider_attempt(self, attempt):
        r = dict(attempt)
        cols = ['attempt_id','provider','series_id','started_at','finished_at','status','latency_ms','schema_error','fallback','source_switch','error_message']
        r.setdefault('fallback', False)
        r.setdefault('source_switch', False)
        r["started_at"] = utc_naive(r.get("started_at"))
        r["finished_at"] = utc_naive(r.get("finished_at"))
        self.connection.execute('INSERT INTO provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING', [r.get(c) for c in cols])


Storage = DuckDBStore


def init_db(path=":memory:"):
    """Compatibility factory used by the CLI and small integrations."""
    return DuckDBStore(path)


def connect(path=":memory:"):
    return DuckDBStore(path)
