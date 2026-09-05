from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cross_asset.ingestion.cftc_evidence import (
    CFTCEvidenceError,
    ingest_cftc_snapshot_with_evidence,
)
from cross_asset.ingestion.cftc_positioning import (
    PARSER_VERSION,
    CFTCReportType,
    cftc_publication_at,
)
from cross_asset.ingestion.origin import DataOrigin
from cross_asset.ingestion.raw_archive import ImmutableRawArchive

FIXTURES = Path(__file__).parents[2] / "fixtures" / "cftc_positioning"


def test_cftc_evidence_sidecar_records_full_hash_and_parser_version(tmp_path):
    payload = (FIXTURES / "synthetic_disaggregated_2025.txt").read_bytes()
    publication = cftc_publication_at(date(2025, 1, 10))
    records, health, evidence, sidecar_path = ingest_cftc_snapshot_with_evidence(
        payload,
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        decision_time="2025-01-15T12:00:00+00:00",
        fetched_at="2025-01-15T12:01:00+00:00",
        publication_at=publication,
        available_at=publication,
        origin=DataOrigin.FIXTURE,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        expected_series=("POS_CFTC_GOLD", "POS_CFTC_COPPER"),
    )

    assert records
    assert health.raw_archive_path is not None
    assert evidence.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert evidence.parser_version == PARSER_VERSION
    assert evidence.source_year == 2025
    assert evidence.row_count == health.row_count
    assert evidence.latest_observation == health.latest_observation
    assert evidence.latest_available_at == health.latest_available_at

    sidecar = Path(sidecar_path)
    assert sidecar == Path(f"{health.raw_archive_path}.meta.json")
    assert sidecar.exists()
    persisted = json.loads(sidecar.read_text(encoding="utf-8"))
    assert persisted["raw_sha256"] == hashlib.sha256(payload).hexdigest()
    assert persisted["parser_version"] == PARSER_VERSION
    assert persisted["source_year"] == 2025
    assert persisted["source_status"] == health.source_status.value


def test_cftc_evidence_sidecar_is_deterministic_for_same_snapshot(tmp_path):
    payload = (FIXTURES / "synthetic_disaggregated_2025.txt").read_bytes()
    publication = cftc_publication_at(date(2025, 1, 10))
    kwargs = {
        "report_type": CFTCReportType.DISAGGREGATED,
        "source_year": 2025,
        "decision_time": "2025-01-15T12:00:00+00:00",
        "fetched_at": datetime(2025, 1, 15, 12, 1, tzinfo=UTC),
        "publication_at": publication,
        "available_at": publication,
        "origin": DataOrigin.FIXTURE,
        "raw_archive": ImmutableRawArchive(tmp_path / "raw"),
        "expected_series": ("POS_CFTC_GOLD", "POS_CFTC_COPPER"),
    }

    first = ingest_cftc_snapshot_with_evidence(payload, **kwargs)
    second = ingest_cftc_snapshot_with_evidence(payload, **kwargs)

    assert first[2] == second[2]
    assert first[3] == second[3]


def test_cftc_evidence_entrypoint_requires_raw_archive():
    payload = (FIXTURES / "synthetic_disaggregated_2025.txt").read_bytes()
    publication = cftc_publication_at(date(2025, 1, 10))
    with pytest.raises(CFTCEvidenceError, match="raw_archive_required"):
        ingest_cftc_snapshot_with_evidence(
            payload,
            report_type=CFTCReportType.DISAGGREGATED,
            source_year=2025,
            decision_time="2025-01-15T12:00:00+00:00",
            fetched_at="2025-01-15T12:01:00+00:00",
            publication_at=publication,
            available_at=publication,
            origin=DataOrigin.FIXTURE,
        )
