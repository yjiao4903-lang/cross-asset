from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cross_asset.ingestion.china_leverage import (
    CANONICAL_SERIES_ID,
    ChinaLeverageDuplicateError,
    ChinaLeverageError,
    ChinaLeverageSourceStatus,
    asof_china_leverage_records,
    conservative_margin_available_at,
    derive_china_leverage_metrics,
    evaluate_china_leverage_source_health,
    ingest_china_leverage_snapshot,
    load_china_leverage_sources,
    parse_china_leverage_snapshot,
    resolve_china_leverage_revisions,
)
from cross_asset.ingestion.origin import DataOrigin
from cross_asset.ingestion.raw_archive import ImmutableRawArchive

FIXTURE = Path(__file__).parents[2] / "fixtures" / "china_leverage" / "synthetic_sse_margin.csv"
SHANGHAI = ZoneInfo("Asia/Shanghai")
INGESTED = datetime(2025, 1, 8, 2, 0, tzinfo=UTC)


def _payload() -> bytes:
    return FIXTURE.read_bytes()


def _parse(payload: bytes | str, **kwargs):
    params = {
        "provider": "sse",
        "origin": DataOrigin.FIXTURE,
        "ingested_at": INGESTED,
    }
    params.update(kwargs)
    return parse_china_leverage_snapshot(payload, **params)


def _daily_payload(count: int = 61) -> str:
    rows = ["TRD_DT,PUB_DT,FIN_VAL,SECU_VAL,TTL_VAL,AVAILABLE_AT"]
    start = date(2025, 1, 1)
    for position in range(count):
        observation = start + timedelta(days=position)
        publication = observation + timedelta(days=1)
        publication_at = datetime.combine(publication, time(9), SHANGHAI).astimezone(UTC)
        rows.append(
            f"{observation.isoformat()},{publication.isoformat()},{1000 + position},"
            f",,{publication_at.isoformat()}"
        )
    return "\n".join(rows) + "\n"


def test_source_config_keeps_one_canonical_series_and_official_identities():
    specs = load_china_leverage_sources()

    assert CANONICAL_SERIES_ID == "POS_CN_RZRQ"
    assert {spec.provider for spec in specs} == {"sse", "szse", "csf"}
    assert next(spec for spec in specs if spec.provider == "sse").source_series_id == "SSE_MARGIN_SUM"


def test_sse_parser_preserves_financing_first_and_optional_lending_null():
    records = _parse(_payload(), source_file="synthetic_sse_margin.csv")

    assert len(records) == 2
    assert all(record.series_id == CANONICAL_SERIES_ID for record in records)
    assert records[0].financing_balance == 1_000_000
    assert records[0].securities_lending_balance == 200_000
    assert records[0].total_balance == 1_200_000
    assert records[1].securities_lending_balance is None
    assert records[1].total_balance == 1_010_000
    assert records[1].metadata["securities_lending_optional"] is True
    assert records[0].publication_at == datetime(2025, 1, 7, 1, 0, tzinfo=UTC)
    assert records[0].available_at == datetime(2025, 1, 7, 1, 0, tzinfo=UTC)
    assert records[0].origin is DataOrigin.FIXTURE
    assert "free_float" not in records[0].as_dict()


def test_total_is_derived_only_when_both_components_exist():
    payload = (
        "TRD_DT,PUB_DT,FIN_VAL,SECU_VAL,TTL_VAL,AVAILABLE_AT\n"
        "2025-01-06,2025-01-07,1000,250,,2025-01-07T09:00:00+08:00\n"
    )
    record = _parse(payload)[0]
    assert record.total_balance == 1250
    assert record.metadata["computed_total_balance"] is True


def test_total_mismatch_is_rejected_instead_of_corrected():
    payload = (
        "TRD_DT,PUB_DT,FIN_VAL,SECU_VAL,TTL_VAL,AVAILABLE_AT\n"
        "2025-01-06,2025-01-07,1000,250,1300,2025-01-07T09:00:00+08:00\n"
    )
    with pytest.raises(ChinaLeverageError, match="total_balance_mismatch"):
        _parse(payload)


def test_t_plus_one_policy_requires_an_explicit_next_session_for_inference():
    next_session = conservative_margin_available_at(
        date(2025, 1, 10), next_session_date=date(2025, 1, 13)
    )
    assert next_session == datetime(2025, 1, 13, 1, 0, tzinfo=UTC)
    with pytest.raises(ChinaLeverageError, match="next_session_date_must_follow"):
        conservative_margin_available_at(date(2025, 1, 10), next_session_date=date(2025, 1, 10))


def test_t_day_close_is_blocked_even_when_a_timestamp_is_present():
    payload = (
        "TRD_DT,PUB_DT,FIN_VAL,SECU_VAL,TTL_VAL,AVAILABLE_AT\n"
        "2025-01-06,2025-01-07,1000,250,1250,2025-01-06T16:00:00+08:00\n"
    )
    with pytest.raises(ChinaLeverageError, match="t_day_data_not_available_at_close"):
        _parse(payload)


def test_availability_is_required_and_timezone_aware():
    missing = _payload().decode().replace(",AVAILABLE_AT", "").replace(",2025-01-07T09:00:00+08:00", "")
    with pytest.raises(ChinaLeverageError, match="available_at_required"):
        _parse(missing)

    naive = _payload().decode().replace("2025-01-07T09:00:00+08:00", "2025-01-07T09:00:00")
    with pytest.raises(ChinaLeverageError, match="available_at_timezone_required"):
        _parse(naive)


def test_provider_and_source_identity_have_no_fallback():
    with pytest.raises(ChinaLeverageError, match="unapproved_source_identity"):
        _parse(_payload(), provider="akshare")
    with pytest.raises(ChinaLeverageError, match="unapproved_source_identity"):
        _parse(_payload(), source_series_id="SSE_MIRROR")


def test_asof_excludes_t_plus_one_record_until_available():
    records = _parse(_payload())

    before = asof_china_leverage_records(records, "2025-01-07T00:59:59+00:00")
    after = asof_china_leverage_records(records, "2025-01-07T01:00:00+00:00")

    assert before == []
    assert len(after) == 1
    assert after[0].observation_date == date(2025, 1, 6)


def test_later_margin_revision_is_selected_only_after_availability():
    original = _parse(_payload())[0]
    revision_at = datetime(2025, 1, 9, 1, 0, tzinfo=UTC)
    revision = replace(
        original,
        financing_balance=1_005_000,
        total_balance=1_205_000,
        publication_at=revision_at,
        available_at=revision_at,
        ingested_at=revision_at + timedelta(minutes=1),
    )

    before = resolve_china_leverage_revisions([original, revision], decision_time=original.available_at)
    after = resolve_china_leverage_revisions([original, revision], decision_time=revision_at)

    assert before[0].financing_balance == 1_000_000
    assert after[0].financing_balance == 1_005_000
    assert after[0].metadata["revision_selected"] is True


def test_same_time_conflicting_margin_report_fails_closed():
    original = _parse(_payload())[0]
    conflict = replace(original, financing_balance=999_999)

    with pytest.raises(ChinaLeverageDuplicateError, match="conflicting_same_time_margin_report"):
        resolve_china_leverage_revisions([original, conflict])


def test_metrics_are_financing_only_causal_and_do_not_fill_lookbacks():
    records = _parse(_daily_payload())
    metrics = derive_china_leverage_metrics(
        records,
        decision_time="2025-03-10T01:00:00+00:00",
        percentile_window=20,
    )

    latest = [metric for metric in metrics if metric.observation_date == date(2025, 3, 2)]
    by_name = {metric.metric: metric for metric in latest}
    assert by_name["financing_balance"].value == 1060
    assert by_name["financing_daily_change"].value == 1
    assert by_name["financing_20d_change"].value == 20
    assert by_name["financing_60d_change"].value == 60
    assert by_name["financing_rolling_percentile"].value == 100

    first = [metric for metric in metrics if metric.observation_date == date(2025, 1, 1)]
    first_by_name = {metric.metric: metric for metric in first}
    assert first_by_name["financing_daily_change"].value is None
    assert first_by_name["financing_20d_change"].value is None
    assert first_by_name["financing_60d_change"].value is None
    assert all("direction" not in metric.metric.lower() for metric in metrics)


def test_source_health_is_explicit_and_raw_snapshot_is_archived(tmp_path):
    records, health = ingest_china_leverage_snapshot(
        _payload(),
        provider="sse",
        decision_time="2025-01-08T02:00:00+00:00",
        fetched_at="2025-01-08T02:01:00+00:00",
        source_file="synthetic_sse_margin.csv",
        origin=DataOrigin.FIXTURE,
        raw_archive=ImmutableRawArchive(tmp_path / "raw"),
    )

    assert len(records) == 2
    assert health.source_status is ChinaLeverageSourceStatus.HEALTHY
    assert health.parser_status == "PASS"
    assert health.coverage_status == "FINANCING_ONLY"
    assert "securities_lending_optional_unavailable" in health.warnings
    assert health.origin is DataOrigin.FIXTURE
    assert health.raw_archive_path is not None and Path(health.raw_archive_path).exists()

    stale = evaluate_china_leverage_source_health(
        records,
        decision_time="2025-02-01T12:00:00+00:00",
        provider="sse",
        source_series_id="SSE_MARGIN_SUM",
        source_file="synthetic_sse_margin.csv",
        max_staleness_days=7,
    )
    assert stale.source_status is ChinaLeverageSourceStatus.STALE


def test_failed_and_unapproved_snapshots_remain_non_consumable():
    malformed = _payload().decode().replace("FIN_VAL", "UNKNOWN_FIN_VAL")
    failed_records, failed = ingest_china_leverage_snapshot(
        malformed,
        provider="sse",
        decision_time="2025-01-08T02:00:00+00:00",
        fetched_at="2025-01-08T02:01:00+00:00",
        origin=DataOrigin.FIXTURE,
    )
    unapproved_records, unapproved = ingest_china_leverage_snapshot(
        _payload(),
        provider="third_party_mirror",
        decision_time="2025-01-08T02:00:00+00:00",
        fetched_at="2025-01-08T02:01:00+00:00",
        origin=DataOrigin.LIVE,
    )

    assert failed_records == [] and failed.source_status is ChinaLeverageSourceStatus.FAILED
    assert unapproved_records == [] and unapproved.source_status is ChinaLeverageSourceStatus.UNAPPROVED
