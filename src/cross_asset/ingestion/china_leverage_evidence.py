"""Immutable C0 provenance sidecar for China leverage raw snapshots.

The W1 C0 shadow-archive contract requires full raw SHA-256 and parser-version
provenance.  The core China leverage parser stays isolated from production
admission; this module persists deterministic metadata next to the existing
content-addressed raw snapshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .china_leverage import (
    PARSER_VERSION,
    ChinaLeverageRecord,
    ChinaLeverageSourceHealth,
    ingest_china_leverage_snapshot,
)


class ChinaLeverageEvidenceError(ValueError):
    """Raised when a C0 raw provenance sidecar cannot be produced safely."""


def _payload_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise ChinaLeverageEvidenceError("payload_must_be_text_or_bytes")


@dataclass(frozen=True)
class ChinaLeverageRawSnapshotEvidence:
    raw_sha256: str
    parser_version: str
    raw_archive_path: str
    provider: str
    source_series_id: str
    source_file: str
    fetched_at: datetime
    row_count: int
    latest_observation: date | None
    latest_available_at: datetime | None
    source_status: str
    parser_status: str
    coverage_status: str
    warnings: tuple[str, ...]
    failure_reason: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "raw_sha256": self.raw_sha256,
            "parser_version": self.parser_version,
            "raw_archive_path": self.raw_archive_path,
            "provider": self.provider,
            "source_series_id": self.source_series_id,
            "source_file": self.source_file,
            "fetched_at": self.fetched_at.isoformat(),
            "row_count": self.row_count,
            "latest_observation": (
                self.latest_observation.isoformat() if self.latest_observation else None
            ),
            "latest_available_at": (
                self.latest_available_at.isoformat() if self.latest_available_at else None
            ),
            "source_status": self.source_status,
            "parser_status": self.parser_status,
            "coverage_status": self.coverage_status,
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
        }


def build_china_leverage_raw_snapshot_evidence(
    payload: bytes | str,
    health: ChinaLeverageSourceHealth,
) -> ChinaLeverageRawSnapshotEvidence:
    """Build the complete raw provenance record for one archived snapshot."""

    if not health.raw_archive_path:
        raise ChinaLeverageEvidenceError("raw_archive_path_required")
    return ChinaLeverageRawSnapshotEvidence(
        raw_sha256=hashlib.sha256(_payload_bytes(payload)).hexdigest(),
        parser_version=PARSER_VERSION,
        raw_archive_path=health.raw_archive_path,
        provider=health.provider,
        source_series_id=health.source_series_id,
        source_file=health.source_file,
        fetched_at=health.fetched_at,
        row_count=health.row_count,
        latest_observation=health.latest_observation,
        latest_available_at=health.latest_available_at,
        source_status=health.source_status.value,
        parser_status=health.parser_status,
        coverage_status=health.coverage_status,
        warnings=health.warnings,
        failure_reason=health.failure_reason,
    )


def persist_china_leverage_raw_snapshot_evidence(
    payload: bytes | str,
    health: ChinaLeverageSourceHealth,
) -> tuple[ChinaLeverageRawSnapshotEvidence, str]:
    """Persist an immutable deterministic ``.meta.json`` provenance sidecar."""

    evidence = build_china_leverage_raw_snapshot_evidence(payload, health)
    sidecar = Path(f"{health.raw_archive_path}.meta.json")
    encoded = json.dumps(
        evidence.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if sidecar.exists():
        if sidecar.read_bytes() != encoded:
            raise ChinaLeverageEvidenceError("raw_evidence_sidecar_collision")
    else:
        sidecar.write_bytes(encoded)
    return evidence, str(sidecar)


def ingest_china_leverage_snapshot_with_evidence(
    payload: bytes | str,
    **kwargs,
) -> tuple[
    list[ChinaLeverageRecord],
    ChinaLeverageSourceHealth,
    ChinaLeverageRawSnapshotEvidence,
    str,
]:
    """Run the C0 ingest and persist its mandatory raw provenance sidecar."""

    if kwargs.get("raw_archive") is None:
        raise ChinaLeverageEvidenceError("raw_archive_required")
    records, health = ingest_china_leverage_snapshot(payload, **kwargs)
    evidence, sidecar_path = persist_china_leverage_raw_snapshot_evidence(payload, health)
    return records, health, evidence, sidecar_path


__all__ = [
    "ChinaLeverageEvidenceError",
    "ChinaLeverageRawSnapshotEvidence",
    "build_china_leverage_raw_snapshot_evidence",
    "ingest_china_leverage_snapshot_with_evidence",
    "persist_china_leverage_raw_snapshot_evidence",
]
