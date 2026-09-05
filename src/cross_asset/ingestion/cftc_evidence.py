"""Immutable C0 provenance sidecar for CFTC raw snapshots.

The W1 C0 contract requires the raw snapshot hash and parser version to be
recorded alongside source-health metadata.  ``ImmutableRawArchive`` keeps the
raw bytes content-addressed; this module writes a deterministic metadata
sidecar next to that archived file without changing the production ingestion
surface or crossing the #18 admission gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .cftc_positioning import (
    PARSER_VERSION,
    CFTCPositionRecord,
    CFTCSourceHealth,
    ingest_cftc_snapshot,
)


class CFTCEvidenceError(ValueError):
    """Raised when an immutable C0 evidence sidecar cannot be produced safely."""


def _payload_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise CFTCEvidenceError("payload_must_be_text_or_bytes")


@dataclass(frozen=True)
class CFTCRawSnapshotEvidence:
    raw_sha256: str
    parser_version: str
    raw_archive_path: str
    provider: str
    source_file: str
    source_year: int
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
            "source_file": self.source_file,
            "source_year": self.source_year,
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


def build_cftc_raw_snapshot_evidence(
    payload: bytes | str,
    health: CFTCSourceHealth,
) -> CFTCRawSnapshotEvidence:
    """Build the complete raw provenance record for one archived snapshot."""

    if not health.raw_archive_path:
        raise CFTCEvidenceError("raw_archive_path_required")
    return CFTCRawSnapshotEvidence(
        raw_sha256=hashlib.sha256(_payload_bytes(payload)).hexdigest(),
        parser_version=PARSER_VERSION,
        raw_archive_path=health.raw_archive_path,
        provider=health.provider,
        source_file=health.source_file,
        source_year=health.source_year,
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


def persist_cftc_raw_snapshot_evidence(
    payload: bytes | str,
    health: CFTCSourceHealth,
) -> tuple[CFTCRawSnapshotEvidence, str]:
    """Persist a deterministic immutable ``.meta.json`` sidecar for the raw file."""

    evidence = build_cftc_raw_snapshot_evidence(payload, health)
    sidecar = Path(f"{health.raw_archive_path}.meta.json")
    encoded = json.dumps(
        evidence.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if sidecar.exists():
        if sidecar.read_bytes() != encoded:
            raise CFTCEvidenceError("raw_evidence_sidecar_collision")
    else:
        sidecar.write_bytes(encoded)
    return evidence, str(sidecar)


def ingest_cftc_snapshot_with_evidence(
    payload: bytes | str,
    **kwargs,
) -> tuple[list[CFTCPositionRecord], CFTCSourceHealth, CFTCRawSnapshotEvidence, str]:
    """Run the C0 ingest and persist the mandatory raw provenance sidecar.

    ``raw_archive`` is mandatory for this evidence-bearing entry point.  The
    wrapped ingest remains C0-only and keeps all production/admission behavior
    disabled exactly as in :func:`ingest_cftc_snapshot`.
    """

    if kwargs.get("raw_archive") is None:
        raise CFTCEvidenceError("raw_archive_required")
    records, health = ingest_cftc_snapshot(payload, **kwargs)
    evidence, sidecar_path = persist_cftc_raw_snapshot_evidence(payload, health)
    return records, health, evidence, sidecar_path


__all__ = [
    "CFTCEvidenceError",
    "CFTCRawSnapshotEvidence",
    "build_cftc_raw_snapshot_evidence",
    "ingest_cftc_snapshot_with_evidence",
    "persist_cftc_raw_snapshot_evidence",
]
