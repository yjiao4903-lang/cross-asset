from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cross_asset.ingestion.cftc_positioning import (
    CFTCPositioningError,
    CFTCReportType,
    cftc_publication_at,
    parse_cftc_snapshot,
)
from cross_asset.ingestion.origin import DataOrigin

FIXTURES = Path(__file__).parents[2] / "fixtures" / "cftc_positioning"
PAYLOAD = (FIXTURES / "synthetic_disaggregated_2025.txt").read_bytes()


def _parse(publication_date: date):
    publication_at = cftc_publication_at(publication_date)
    return parse_cftc_snapshot(
        PAYLOAD,
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        publication_at=publication_at,
        available_at=publication_at,
        origin=DataOrigin.FIXTURE,
    )


def test_publication_before_tuesday_report_date_is_rejected():
    with pytest.raises(
        CFTCPositioningError,
        match="publication_at_must_be_after_report_date",
    ):
        _parse(date(2025, 1, 6))


def test_publication_on_same_tuesday_report_date_is_rejected():
    with pytest.raises(
        CFTCPositioningError,
        match="publication_at_must_be_after_report_date",
    ):
        _parse(date(2025, 1, 7))


def test_caller_supplied_holiday_shifted_monday_release_is_preserved():
    records = _parse(date(2025, 1, 13))
    assert records
    assert {record.report_date for record in records} == {date(2025, 1, 7)}
    assert {record.publication_at.date() for record in records} == {date(2025, 1, 13)}
