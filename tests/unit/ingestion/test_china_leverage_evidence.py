from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cross_asset.ingestion.china_leverage import PARSER_VERSION
from cross_asset.ingestion.china_leverage_evidence import (
    ChinaLeverageEvidenceError,
    ingest_china_leverage_snapshot_with_evidence,
)
from cross_asset.ingestion.origin import DataOrigin
from cross_asset.ingestion.raw_archive import ImmutableRawArchive

FIXTURES = Path(__file__).parents[2] / "fixtures" / "china_leverage"


def test_china_leverage_sidecar_records_full_hash_and_parser_version(tmp_path):
    payload = (FIXTURES / "synthetic_sse_margin.csv").read_bytes()
    records, health, evidence, sidecar_path = ingest_china_leverage_snapshot_with_evidence(
        payload,
        provider="sse",
        source_series_id="SSE_MARGIN_SUM",
        decision_time="2025-01-09T09:00:00+08:00",
        fetched_at="2025-01-09T09:01:00+08:00",
        origin=DataOrigin.FIXTURE,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
    )

    assert records
    assert health.raw_archive_path is not None
    assert evidence.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert evidence.parser_version == PARSER_VERSION
    assert evidence.provider == "sse"
    assert evidence.source_series_id == "SSE_MARGIN_SUM"
    assert evidence.row_count == health.row_count
    assert evidence.latest_observation == health.latest_observation
    assert evidence.latest_available_at == health.latest_available_at

    sidecar = Path(sidecar_path)
    assert sidecar == Path(f"{health.raw_archive_path}.meta.json")
    assert sidecar.exists()
    persisted = json.loads(sidecar.read_text(encoding="utf-8"))
    assert persisted["raw_sha256"] == hashlib.sha256(payload).hexdigest()
    assert persisted["parser_version"] == PARSER_VERSION
    assert persisted["source_series_id"] == "SSE_MARGIN_SUM"
    assert persisted["source_status"] == health.source_status.value


def test_china_leverage_sidecar_is_deterministic_for_same_snapshot(tmp_path):
    payload = (FIXTURES / "synthetic_sse_margin.csv").read_bytes()
    kwargs = {
        "provider": "sse",
        "source_series_id": "SSE_MARGIN_SUM",
        "decision_time": "2025-01-09T09:00:00+08:00",
        "fetched_at": datetime(2025, 1, 9, 1, 1, tzinfo=UTC),
        "origin": DataOrigin.FIXTURE,
        "raw_archive": ImmutableRawArchive(tmp_path / "raw"),
    }

    first = ingest_china_leverage_snapshot_with_evidence(payload, **kwargs)
    second = ingest_china_leverage_snapshot_with_evidence(payload, **kwargs)

    assert first[2] == second[2]
    assert first[3] == second[3]


def test_china_leverage_evidence_entrypoint_requires_raw_archive():
    payload = (FIXTURES / "synthetic_sse_margin.csv").read_bytes()
    with pytest.raises(ChinaLeverageEvidenceError, match="raw_archive_required"):
        ingest_china_leverage_snapshot_with_evidence(
            payload,
            provider="sse",
            source_series_id="SSE_MARGIN_SUM",
            decision_time="2025-01-09T09:00:00+08:00",
            fetched_at="2025-01-09T09:01:00+08:00",
            origin=DataOrigin.FIXTURE,
        )
