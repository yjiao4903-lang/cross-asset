"""Monitoring-only ingestion orchestration.

This lane may persist canonical observations for operational visibility, but it
never writes the acceptance registry and therefore never grants formal usage.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4

from cross_asset.ingestion.normalization import normalize_observation
from cross_asset.storage.catalog import (
    expected_source_identities,
    sync_series_catalog,
    update_catalog_from_monitoring_rows,
)


def _now_naive():
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_error(error) -> str:
    if error is None:
        return "monitoring provider returned no rows"
    if isinstance(error, dict):
        return str(error.get("message") or error.get("safe_error") or error)[:240]
    return str(error)[:240]


class MonitoringRunner:
    """Persist monitoring observations with explicit non-formal run lineage."""

    def __init__(
        self,
        store,
        provider,
        *,
        raw_archive=None,
        series_config="config/series.yml",
        sources_config="config/sources.yml",
    ):
        self.store = store
        self.provider = provider
        self.raw_archive = raw_archive
        self.series_config = series_config
        self.sources_config = sources_config

    @property
    def provider_name(self) -> str:
        return str(getattr(self.provider, "name", self.provider)).lower()

    def _record_attempt(
        self,
        series_id,
        *,
        started_at,
        finished_at,
        status,
        latency_ms,
        schema_error=None,
        error_message=None,
    ):
        self.store.record_provider_attempt(
            {
                "attempt_id": str(uuid4()),
                "provider": self.provider_name,
                "series_id": str(series_id),
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "latency_ms": latency_ms,
                "schema_error": schema_error,
                "fallback": False,
                "source_switch": False,
                "error_message": error_message,
            }
        )

    def _record_quality(self, series_id, *, run_id, event_type, severity, message):
        self.store.record_quality_event(
            {
                "event_id": str(uuid4()),
                "detected_at": _now_naive(),
                "series_id": str(series_id),
                "severity": severity,
                "event_type": event_type,
                "message": message,
                "provider": self.provider_name,
                "run_id": run_id,
            }
        )

    def _validate_rows(self, rows, requested_series):
        expected = expected_source_identities(
            self.store.conn, self.provider_name, requested_series
        )
        errors: dict[str, list[str]] = {}
        for row in rows:
            sid = str(row.get("series_id") or "")
            if sid not in requested_series:
                errors.setdefault(sid or "UNKNOWN", []).append(
                    "monitoring_series_not_requested"
                )
                continue
            source = str(row.get("source") or "").lower()
            if source != self.provider_name:
                errors.setdefault(sid, []).append(
                    f"monitoring_source_mismatch:{source or 'missing'}"
                )
            source_series_id = str(row.get("source_series_id") or "")
            allowed = expected.get(sid) or set()
            if not allowed:
                errors.setdefault(sid, []).append(
                    "monitoring_source_mapping_missing"
                )
            elif source_series_id not in allowed:
                errors.setdefault(sid, []).append(
                    f"monitoring_source_series_id_mismatch:{source_series_id or 'missing'}"
                )
            metadata = row.get("metadata") or {}
            if str(metadata.get("origin") or "").upper() != "MONITORING":
                errors.setdefault(sid, []).append(
                    "monitoring_origin_marker_required"
                )
            if row.get("available_at") is None:
                errors.setdefault(sid, []).append("monitoring_available_at_required")
        return {key: sorted(set(value)) for key, value in errors.items()}

    def run(self, request, *, run_id=None):
        requested_series = [str(value) for value in request.series_ids]
        run_id = str(run_id or f"monitoring-{self.provider_name}-{uuid4()}")
        catalog = sync_series_catalog(
            self.store,
            series_ids=requested_series,
            provider=self.provider_name,
            series_config=self.series_config,
            sources_config=self.sources_config,
        )
        run_provider = f"MONITORING:{self.provider_name}"
        started_at = _now_naive()
        self.store.start_run(
            run_provider,
            run_id,
            requested_series=len(requested_series),
            started_at=started_at,
        )
        started_clock = time.perf_counter()
        try:
            fetched = list(self.provider.fetch(request) or [])
        except Exception as exc:  # noqa: BLE001 - provider failures are monitoring evidence
            latency_ms = round((time.perf_counter() - started_clock) * 1000, 2)
            finished_at = _now_naive()
            message = _safe_error(exc)
            for sid in requested_series:
                self._record_attempt(
                    sid,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="FAILED",
                    latency_ms=latency_ms,
                    error_message=message,
                )
                self._record_quality(
                    sid,
                    run_id=run_id,
                    event_type="MONITORING_FETCH_ERROR",
                    severity="ERROR",
                    message=message,
                )
            self.store.finish_run(
                run_id,
                "failed",
                success_series=0,
                failed_series=len(requested_series),
                rows_written=0,
                error_summary=message,
            )
            return {
                "run_id": run_id,
                "lane": "MONITORING",
                "status": "failed",
                "rows_written": 0,
                "errors": {"provider": [message]},
                "formal_admission_attempted": False,
                **catalog,
            }

        latency_ms = round((time.perf_counter() - started_clock) * 1000, 2)
        provider_error = getattr(self.provider, "last_error", None)
        if provider_error and not fetched:
            message = _safe_error(provider_error)
            finished_at = _now_naive()
            for sid in requested_series:
                self._record_attempt(
                    sid,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="FAILED",
                    latency_ms=latency_ms,
                    error_message=message,
                )
                self._record_quality(
                    sid,
                    run_id=run_id,
                    event_type="MONITORING_FETCH_ERROR",
                    severity="ERROR",
                    message=message,
                )
            self.store.finish_run(
                run_id,
                "failed",
                success_series=0,
                failed_series=len(requested_series),
                rows_written=0,
                error_summary=message,
            )
            return {
                "run_id": run_id,
                "lane": "MONITORING",
                "status": "failed",
                "rows_written": 0,
                "errors": {"provider": [message]},
                "formal_admission_attempted": False,
                **catalog,
            }

        normalized = []
        for item in fetched:
            if hasattr(item, "available_at"):
                item = normalize_observation(item)
                row = item.model_dump(mode="json")
            else:
                row = dict(item)
            normalized.append(row)

        errors = self._validate_rows(normalized, set(requested_series))
        if errors:
            finished_at = _now_naive()
            message = "; ".join(
                f"{sid}:{','.join(reasons)}" for sid, reasons in sorted(errors.items())
            )[:240]
            for sid in requested_series:
                reasons = errors.get(sid)
                self._record_attempt(
                    sid,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="SCHEMA_ERROR" if reasons else "FAILED",
                    latency_ms=latency_ms,
                    schema_error=";".join(reasons) if reasons else None,
                    error_message=message,
                )
                self._record_quality(
                    sid,
                    run_id=run_id,
                    event_type="MONITORING_SCHEMA_ERROR",
                    severity="ERROR",
                    message=message,
                )
            self.store.finish_run(
                run_id,
                "failed",
                success_series=0,
                failed_series=len(requested_series),
                rows_written=0,
                error_summary=message,
            )
            return {
                "run_id": run_id,
                "lane": "MONITORING",
                "status": "failed",
                "rows_written": 0,
                "errors": errors,
                "formal_admission_attempted": False,
                **catalog,
            }

        raw_file = None
        if self.raw_archive is not None and normalized:
            raw_file = self.raw_archive.write(
                self.provider_name,
                "monitoring_observations",
                normalized,
            )
        if raw_file:
            for row in normalized:
                row["raw_file"] = raw_file

        written = self.store.insert_observations(normalized, run_id=run_id)
        update_catalog_from_monitoring_rows(self.store, normalized)

        returned = {str(row["series_id"]) for row in normalized if row.get("series_id")}
        finished_at = _now_naive()
        for sid in requested_series:
            if sid in returned:
                self._record_attempt(
                    sid,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="SUCCESS",
                    latency_ms=latency_ms,
                )
                self._record_quality(
                    sid,
                    run_id=run_id,
                    event_type="MONITORING_OK",
                    severity="INFO",
                    message="monitoring observation persisted; formal usage unchanged",
                )
            else:
                self._record_attempt(
                    sid,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="FAILED",
                    latency_ms=latency_ms,
                    error_message="monitoring provider returned no row for series",
                )
                self._record_quality(
                    sid,
                    run_id=run_id,
                    event_type="MONITORING_MISSING",
                    severity="WARN",
                    message="monitoring provider returned no row for series",
                )

        status = "success" if len(returned) == len(requested_series) else (
            "partial" if returned else "empty"
        )
        self.store.finish_run(
            run_id,
            status,
            success_series=len(returned),
            failed_series=max(0, len(requested_series) - len(returned)),
            rows_written=written,
        )
        return {
            "run_id": run_id,
            "lane": "MONITORING",
            "status": status,
            "requested_series_count": len(requested_series),
            "returned_series_count": len(returned),
            "rows_written": written,
            "raw_file": raw_file,
            "formal_admission_attempted": False,
            "errors": {},
            **catalog,
        }


__all__ = ["MonitoringRunner"]
