"""Provider-independent ingestion orchestration."""

import inspect
import math
from uuid import uuid4

from .normalization import normalize_observation


def _series_counts(rows):
    """Split returned rows into distinct series and series with a valid value."""

    returned = {str(row.get("series_id")) for row in rows if row.get("series_id")}
    valid = set()
    for row in rows:
        value = row.get("value")
        if row.get("series_id") and value is not None:
            try:
                if math.isfinite(float(value)):
                    valid.add(str(row["series_id"]))
            except (TypeError, ValueError):
                continue
    return returned, valid


class IngestionRunner:
    def __init__(self, store, raw_archive=None):
        self.store, self.raw_archive = store, raw_archive

    def run(self, provider, fetch, requests=None, *, run_id=None):
        run_id = str(run_id or uuid4())
        requested = (
            (len(requests.series_ids) if hasattr(requests, "series_ids") else len(requests))
            if requests is not None
            else None
        )
        provider_name = getattr(provider, "name", provider)
        self.store.start_run(provider_name, run_id, requested)
        rows = []
        success = failed = 0
        try:
            # Provider adapters accept a request object (possibly None), while
            # simple test/manual callables may intentionally take no arguments.
            # Inspect the callable rather than catching TypeError from inside it.
            if requests is not None or len(inspect.signature(fetch).parameters):
                result = fetch(requests)
            else:
                result = fetch()
            rows = list(result or [])
            provider_error = getattr(provider, "last_error", None)
            if provider_error and not rows:
                self.store.finish_run(
                    run_id,
                    "failed",
                    success_series=0,
                    failed_series=1,
                    rows_written=0,
                    error_summary=provider_error.get("message", "provider failure"),
                )
                if hasattr(self.store, "record_provider_attempt"):
                    self.store.record_provider_attempt({"attempt_id": str(uuid4()), "provider": provider_name, "series_id": "*", "started_at": self.store.query("SELECT started_at FROM ingestion_runs WHERE run_id=?", [run_id]).fetchone()[0], "finished_at": __import__("datetime").datetime.now(__import__("datetime").UTC).replace(tzinfo=None), "status": "FAILED", "schema_error": provider_error.get("code") or provider_error.get("error_type"), "error_message": provider_error.get("message")})
                return {
                    "run_id": run_id,
                    "status": "failed",
                    "requested_series_count": requested,
                    "returned_series_count": 0,
                    "valid_series_count": 0,
                    "rows_written": 0,
                    "error": provider_error,
                }
            # Normalize mapping-like records without taking ownership of provider models.
            # Normalize before archiving/writing so stored observations share one
            # timezone/scalar contract while preserving missing values.
            normalized = []
            for row in rows:
                if hasattr(row, "available_at"):
                    row = normalize_observation(row)
                    metadata = dict(row.metadata or {})
                    metadata.setdefault("origin", "MANUAL" if str(provider_name).lower() == "manual" else "UNAVAILABLE")
                    row.metadata = metadata
                normalized.append(
                    row.model_dump(mode="json") if hasattr(row, "model_dump") else dict(row)
                )
            rows = normalized
            raw_file = None
            if self.raw_archive is not None and rows:
                raw_file = self.raw_archive.write(provider_name, "observations", rows)
            if raw_file:
                for row in rows:
                    row.setdefault("raw_file", raw_file)
            written = self.store.insert_observations(rows, run_id)
            # Requested, returned, valid and persisted series counts are kept
            # distinct: an empty or partial provider return must never be
            # recorded as an unqualified success (Issue #18).
            returned_series, valid_series = _series_counts(rows)
            if not rows:
                run_status = "empty"
            elif requested is not None and len(returned_series) < requested:
                run_status = "partial"
            else:
                run_status = "success"
            success = len(valid_series)
            self.store.finish_run(
                run_id,
                run_status,
                success_series=success,
                failed_series=max(0, len(returned_series) - len(valid_series)),
                rows_written=written,
            )
            return {
                "run_id": run_id,
                "status": run_status,
                "requested_series_count": requested,
                "returned_series_count": len(returned_series),
                "valid_series_count": len(valid_series),
                "rows_written": written,
            }
        except Exception as exc:
            self.store.finish_run(
                run_id,
                "failed",
                success_series=success,
                failed_series=max(1, failed),
                rows_written=0,
                error_summary=str(exc),
            )
            raise


def ingest(provider, fetch, store, requests=None, raw_archive=None, run_id=None):
    return IngestionRunner(store, raw_archive).run(provider, fetch, requests, run_id=run_id)
