from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from cross_asset.ingestion.cftc_positioning import (
    CFTCDuplicateReportError,
    CFTCPositioningError,
    CFTCReportType,
    CFTCSourceStatus,
    asof_cftc_records,
    cftc_publication_at,
    derive_net_position,
    derive_percent_open_interest,
    derive_positioning_metrics,
    evaluate_cftc_source_health,
    ingest_cftc_snapshot,
    load_cftc_contracts,
    parse_cftc_snapshot,
    resolve_cftc_revisions,
)
from cross_asset.ingestion.origin import DataOrigin
from cross_asset.ingestion.raw_archive import ImmutableRawArchive

FIXTURES = Path(__file__).parents[2] / "fixtures" / "cftc_positioning"
REPORT_DATE = date(2025, 1, 7)
PUBLICATION = cftc_publication_at(date(2025, 1, 10))
AVAILABLE = PUBLICATION + timedelta(minutes=5)
INGESTED = datetime(2025, 1, 10, 21, 0, tzinfo=UTC)


def _payload(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _parse(payload: bytes | str, report_type: CFTCReportType, **kwargs):
    params = {
        "report_type": report_type,
        "source_year": 2025,
        "publication_at": PUBLICATION,
        "available_at": AVAILABLE,
        "ingested_at": INGESTED,
        "origin": DataOrigin.FIXTURE,
    }
    params.update(kwargs)
    return parse_cftc_snapshot(payload, **params)


def _zip_payload(member: str, payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, payload)
    return output.getvalue()


def _long_layout(rows: list[str]) -> str:
    return (
        "report_date,contract_market_code,participant_category,long,short,spreading,"
        "open_interest,publication_at,available_at\n"
        + "\n".join(rows)
        + "\n"
    )


def test_cftc_mapping_is_centralized_and_covers_required_contracts():
    specs = load_cftc_contracts()
    assert {(spec.series_id, spec.report_type) for spec in specs} == {
        ("POS_CFTC_GOLD", CFTCReportType.DISAGGREGATED),
        ("POS_CFTC_COPPER", CFTCReportType.DISAGGREGATED),
        ("POS_CFTC_SP500", CFTCReportType.TFF),
        ("POS_CFTC_US10Y", CFTCReportType.TFF),
    }
    sp500 = next(spec for spec in specs if spec.series_id == "POS_CFTC_SP500")
    assert set(sp500.contract_market_codes) == {"13874A", "13874+"}


def test_disaggregated_wide_annual_layout_emits_all_participant_categories():
    records = _parse(_payload("synthetic_disaggregated_2025.txt"), CFTCReportType.DISAGGREGATED)

    assert len(records) == 10
    gold = [record for record in records if record.series_id == "POS_CFTC_GOLD"]
    assert {record.participant_category for record in gold} == {
        "PRODUCER_MERCHANT",
        "SWAP_DEALER",
        "MANAGED_MONEY",
        "OTHER_REPORTABLE",
        "NONREPORTABLE",
    }
    managed = next(record for record in gold if record.participant_category == "MANAGED_MONEY")
    assert managed.contract_market_code == "088691"
    assert managed.spreading == 30
    assert derive_net_position(managed) == 150
    assert derive_percent_open_interest(managed) == 15
    assert managed.source_year == 2025
    assert managed.origin is DataOrigin.FIXTURE


def test_tff_zip_layout_and_source_member_are_supported():
    records = _parse(
        _zip_payload("FinCom25.txt", _payload("synthetic_tff_2025.txt")),
        CFTCReportType.TFF,
        source_file="com_fin_txt_2025.zip",
    )

    assert len(records) == 10
    assert {record.series_id for record in records} == {"POS_CFTC_SP500", "POS_CFTC_US10Y"}
    assert {record.source_file for record in records} == {"com_fin_txt_2025.zip"}
    assert all(record.report_type is CFTCReportType.TFF for record in records)


def test_normalized_long_layout_supports_contract_code_alias_and_participant_alias():
    payload = _long_layout(
        [
            (
                f"2025-01-07,13874+,Dealer,110,90,,5000,{PUBLICATION.isoformat()},"
                f"{AVAILABLE.isoformat()}"
            )
        ]
    )
    records = _parse(payload, CFTCReportType.TFF, source_file="FinCom25.txt")

    assert len(records) == 1
    assert records[0].series_id == "POS_CFTC_SP500"
    assert records[0].contract_market_code == "13874+"
    assert records[0].participant_category == "DEALER_INTERMEDIARY"
    assert records[0].spreading is None


def test_publication_helper_uses_eastern_time_and_does_not_guess_holiday_shift():
    normal = cftc_publication_at(date(2025, 1, 10))
    holiday_shifted = cftc_publication_at(date(2025, 1, 13))

    assert normal == datetime(2025, 1, 10, 20, 30, tzinfo=UTC)
    assert holiday_shifted == datetime(2025, 1, 13, 20, 30, tzinfo=UTC)


def test_publication_is_required_and_never_falls_back_to_observation_date():
    with pytest.raises(CFTCPositioningError, match="publication_at_required"):
        parse_cftc_snapshot(
            _payload("synthetic_disaggregated_2025.txt"),
            report_type=CFTCReportType.DISAGGREGATED,
            source_year=2025,
        )


def test_available_at_cannot_precede_actual_publication():
    with pytest.raises(CFTCPositioningError, match="available_at_before_publication_at"):
        _parse(
            _payload("synthetic_disaggregated_2025.txt"),
            CFTCReportType.DISAGGREGATED,
            available_at=PUBLICATION - timedelta(seconds=1),
        )


def test_report_date_must_be_tuesday():
    payload = _payload("synthetic_disaggregated_2025.txt").decode().replace(
        "2025-01-07", "2025-01-08"
    )
    with pytest.raises(CFTCPositioningError, match="report_date_must_be_tuesday"):
        _parse(payload, CFTCReportType.DISAGGREGATED)


def test_missing_participant_column_is_a_hard_parse_failure():
    payload = _payload("synthetic_disaggregated_2025.txt").decode().replace(
        "M_Money_Positions_Long_All", "Unknown_Long_All"
    )
    with pytest.raises(CFTCPositioningError, match="MANAGED_MONEY:long_column_missing"):
        _parse(payload, CFTCReportType.DISAGGREGATED)


def test_asof_excludes_friday_release_until_publication_is_known():
    records = _parse(_payload("synthetic_disaggregated_2025.txt"), CFTCReportType.DISAGGREGATED)

    before_release = asof_cftc_records(records, "2025-01-10T20:29:59+00:00")
    after_release = asof_cftc_records(records, "2025-01-10T20:35:00+00:00")

    assert before_release == []
    assert len(after_release) == 10
    assert all(record.available_at <= datetime(2025, 1, 10, 20, 35, tzinfo=UTC) for record in after_release)


def test_later_republication_is_selected_only_after_its_availability():
    records = _parse(_payload("synthetic_disaggregated_2025.txt"), CFTCReportType.DISAGGREGATED)
    original = next(record for record in records if record.participant_category == "MANAGED_MONEY")
    revised_at = cftc_publication_at(date(2025, 1, 13))
    revision = replace(
        original,
        long=350,
        publication_at=revised_at,
        available_at=revised_at,
        ingested_at=revised_at + timedelta(minutes=1),
    )

    before_revision = resolve_cftc_revisions(records + [revision], decision_time=AVAILABLE)
    after_revision = resolve_cftc_revisions(records + [revision], decision_time=revised_at)
    selected = next(
        record
        for record in after_revision
        if record.series_id == "POS_CFTC_GOLD" and record.participant_category == "MANAGED_MONEY"
    )

    before_selected = next(
        record
        for record in before_revision
        if record.series_id == "POS_CFTC_GOLD" and record.participant_category == "MANAGED_MONEY"
    )
    assert before_selected.long == 300
    assert selected.series_id == "POS_CFTC_GOLD"
    assert selected.long == 350
    assert selected.metadata["revision_selected"] is True


def test_same_time_conflicting_republication_is_not_silently_deduplicated():
    records = _parse(_payload("synthetic_disaggregated_2025.txt"), CFTCReportType.DISAGGREGATED)
    original = next(record for record in records if record.participant_category == "MANAGED_MONEY")
    conflict = replace(original, long=999)

    with pytest.raises(CFTCDuplicateReportError, match="conflicting_same_time_report"):
        resolve_cftc_revisions([original, conflict])


def test_research_metrics_are_causal_and_do_not_create_directional_labels():
    payload = _long_layout(
        [
            (
                f"2025-01-07,13874+,Dealer,110,90,,5000,{PUBLICATION.isoformat()},"
                f"{AVAILABLE.isoformat()}"
            ),
            (
                f"2025-01-14,13874+,Dealer,220,90,,5000,{cftc_publication_at(date(2025, 1, 17)).isoformat()},"
                f"{cftc_publication_at(date(2025, 1, 17)).isoformat()}"
            ),
        ]
    )
    records = parse_cftc_snapshot(
        payload,
        report_type=CFTCReportType.TFF,
        source_year=2025,
        origin=DataOrigin.FIXTURE,
        ingested_at=INGESTED,
    )

    before_second_release = derive_positioning_metrics(
        records, decision_time="2025-01-16T12:00:00+00:00", percentile_window=156, zscore_window=2
    )
    after_second_release = derive_positioning_metrics(
        records, decision_time="2025-01-20T12:00:00+00:00", percentile_window=156, zscore_window=2
    )

    assert {metric.report_date for metric in before_second_release} == {date(2025, 1, 7)}
    latest_z = [
        metric
        for metric in after_second_release
        if metric.metric == "causal_zscore" and metric.report_date == date(2025, 1, 14)
    ]
    assert len(latest_z) == 1 and latest_z[0].value is not None
    assert all(metric.metric not in {"LONG", "SHORT", "BUY", "SELL"} for metric in after_second_release)


def test_source_health_archives_snapshot_and_separates_partial_and_stale(tmp_path):
    payload = _payload("synthetic_disaggregated_2025.txt")
    records, health = ingest_cftc_snapshot(
        payload,
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        decision_time="2025-01-15T12:00:00+00:00",
        fetched_at="2025-01-15T12:01:00+00:00",
        publication_at=PUBLICATION,
        available_at=AVAILABLE,
        origin=DataOrigin.FIXTURE,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
        expected_series=("POS_CFTC_GOLD", "POS_CFTC_COPPER"),
    )

    assert len(records) == 10
    assert health.source_status is CFTCSourceStatus.HEALTHY
    assert health.parser_status == "PASS"
    assert health.coverage_status == "COMPLETE"
    assert health.origin is DataOrigin.FIXTURE
    assert health.raw_archive_path is not None and Path(health.raw_archive_path).exists()

    partial = ingest_cftc_snapshot(
        payload.split(b"Copper - COMEX")[0] + b"\n",
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        decision_time="2025-01-15T12:00:00+00:00",
        fetched_at="2025-01-15T12:01:00+00:00",
        publication_at=PUBLICATION,
        available_at=AVAILABLE,
        origin=DataOrigin.FIXTURE,
        expected_series=("POS_CFTC_GOLD", "POS_CFTC_COPPER"),
    )
    assert partial[1].source_status is CFTCSourceStatus.PARTIAL

    stale_health = evaluate_cftc_source_health(
        records,
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        source_file="synthetic_disaggregated_2025.txt",
        decision_time="2025-03-01T12:00:00+00:00",
        expected_series=("POS_CFTC_GOLD", "POS_CFTC_COPPER"),
        max_staleness_days=14,
    )
    assert stale_health.source_status is CFTCSourceStatus.STALE


def test_failed_and_unapproved_snapshots_are_explicit(tmp_path):
    malformed = _payload("synthetic_disaggregated_2025.txt").decode().replace(
        "M_Money_Positions_Long_All", "Unknown_Long_All"
    )
    failed_records, failed = ingest_cftc_snapshot(
        malformed,
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        decision_time="2025-01-15T12:00:00+00:00",
        fetched_at="2025-01-15T12:01:00+00:00",
        publication_at=PUBLICATION,
        origin=DataOrigin.FIXTURE,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
    )
    unapproved_records, unapproved = ingest_cftc_snapshot(
        _payload("synthetic_disaggregated_2025.txt"),
        report_type=CFTCReportType.DISAGGREGATED,
        source_year=2025,
        decision_time="2025-01-15T12:00:00+00:00",
        fetched_at="2025-01-15T12:01:00+00:00",
        publication_at=PUBLICATION,
        provider="community_mirror",
        origin=DataOrigin.LIVE,
    )

    assert failed_records == [] and failed.source_status is CFTCSourceStatus.FAILED
    assert unapproved_records == [] and unapproved.source_status is CFTCSourceStatus.UNAPPROVED
