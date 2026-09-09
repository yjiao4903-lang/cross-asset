from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from cross_asset.ingestion.cftc_c0_contract import (
    PRODUCTION_ADMISSION,
    nominal_friday_publication_at,
    reject_guessed_friday_before_actual_release,
    require_c0_only,
    visible_asof,
)
from cross_asset.ingestion.cftc_positioning import (
    CFTCPositioningError,
    CFTCReportType,
    cftc_publication_at,
    parse_cftc_snapshot,
)
from cross_asset.ingestion.origin import DataOrigin

FIXTURES = Path(__file__).parents[2] / "fixtures" / "cftc_positioning"
REPORT_DATE = date(2025, 1, 7)
PUBLICATION = cftc_publication_at(date(2025, 1, 10))
AVAILABLE = PUBLICATION + timedelta(minutes=5)


def _records():
    return parse_cftc_snapshot(
        (FIXTURES / "synthetic_disaggregated_2025.txt").read_bytes(),
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        publication_at=PUBLICATION,
        available_at=AVAILABLE,
        origin=DataOrigin.FIXTURE,
    )


def test_c0_contract_forbids_production_admission():
    banner = require_c0_only()
    assert banner["gate"] == "C0"
    assert banner["usage"] == "CANDIDATE_ONLY"
    assert PRODUCTION_ADMISSION is False
    assert banner["production_admission"] is False
    assert banner["directional_alpha"] is False
    assert banner["approved_observations"] is False


def test_nominal_friday_is_three_calendar_days_after_tuesday():
    assert nominal_friday_publication_at(REPORT_DATE) == PUBLICATION
    with pytest.raises(CFTCPositioningError, match="report_date_must_be_tuesday"):
        nominal_friday_publication_at(date(2025, 1, 8))


def test_thursday_decision_cannot_see_tuesday_report():
    records = _records()
    leaked = visible_asof(records, "2025-01-09T20:30:00+00:00")
    assert leaked == []


def test_guessed_friday_before_monday_holiday_release_is_rejected():
    actual = cftc_publication_at(date(2025, 1, 13))
    with pytest.raises(
        CFTCPositioningError,
        match="future_leakage_guessed_friday_before_actual_holiday_release",
    ):
        reject_guessed_friday_before_actual_release(
            report_date=REPORT_DATE,
            claimed_publication_at=PUBLICATION,
            actual_publication_at=actual,
        )


def test_actual_monday_holiday_release_is_accepted():
    actual = cftc_publication_at(date(2025, 1, 13))
    reject_guessed_friday_before_actual_release(
        report_date=REPORT_DATE,
        claimed_publication_at=actual,
        actual_publication_at=actual,
    )


def test_older_yymmdd_header_alias_parses_mapped_gold_row():
    payload = (FIXTURES / "synthetic_disaggregated_legacy_headers_2024.txt").read_text(
        encoding="utf-8"
    )
    records = parse_cftc_snapshot(
        payload,
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2024,
        publication_at=PUBLICATION,
        available_at=AVAILABLE,
        origin=DataOrigin.FIXTURE,
    )
    assert {record.series_id for record in records} == {"POS_CFTC_GOLD"}
    assert {record.report_date for record in records} == {REPORT_DATE}
    assert {record.contract_market_code for record in records} == {"088691"}
