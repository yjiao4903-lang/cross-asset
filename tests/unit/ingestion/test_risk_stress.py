"""C0 Risk Stress foundation tests (Issue #38).

All CSV inputs are SYNTHETIC test fixtures under tests/fixtures/risk_stress/
(see that directory's README).  Nothing here is real-data acceptance.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cross_asset.ingestion.raw_archive import ImmutableRawArchive
from cross_asset.ingestion.risk_stress import (
    PARSER_VERSION,
    RiskStressError,
    RiskStressSeries,
    SourceRole,
    SourceStatus,
    SpliceViolationError,
    UnapprovedSourceError,
    asof_records,
    check_series_identity,
    classify_term_structure,
    compute_vix_term_structure,
    evaluate_series_state,
    ingest_source_snapshot,
    parse_risk_stress_csv,
    source_contract,
    vix3m_contract,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "risk_stress"

DECISION_TIME = datetime(2026, 1, 12, tzinfo=UTC)
VIX3M_LEG = "RISK_VIX3M"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse_vix(text: str):
    return parse_risk_stress_csv(
        text, series=RiskStressSeries.VIX_LEVEL, provider="cboe", origin="FIXTURE"
    )


# ---------------------------------------------------------------------------
# 1. VIX3M missing


def test_vix3m_missing_leg_yields_missing_denominator_not_a_ratio():
    vix = _parse_vix(_read("synthetic_vix_close.csv"))
    points = compute_vix_term_structure(vix, vix3m=[])
    assert points, "dates present only in the numerator must still be represented"
    assert all(p.state == "MISSING_DENOMINATOR" for p in points)
    assert all(p.ratio is None and p.available_at is None for p in points)


# ---------------------------------------------------------------------------
# 2. denominator <= 0


def test_non_positive_denominator_is_invalid_not_computed():
    vix = _parse_vix(_read("synthetic_vix_close.csv"))
    broken = _read("synthetic_vix3m_close.csv").replace("19.35", "0.0")
    vix3m = parse_risk_stress_csv(
        broken, series=VIX3M_LEG, provider="cboe", origin="FIXTURE"
    )
    points = compute_vix_term_structure(vix, vix3m)
    bad = [p for p in points if p.state == "INVALID_DENOMINATOR"]
    assert len(bad) == 1 and bad[0].observation_date == date(2026, 1, 6)
    assert bad[0].ratio is None
    ok = [p for p in points if p.state == "OK"]
    assert ok, "other dates must still compute"


def test_negative_denominator_is_invalid():
    vix = _parse_vix(_read("synthetic_vix_close.csv"))
    broken = _read("synthetic_vix3m_close.csv").replace("19.35", "-19.35")
    vix3m = parse_risk_stress_csv(
        broken, series=VIX3M_LEG, provider="cboe", origin="FIXTURE"
    )
    assert any(
        p.state == "INVALID_DENOMINATOR" and p.ratio is None
        for p in compute_vix_term_structure(vix, vix3m)
    )


# ---------------------------------------------------------------------------
# 3. VIX / VIX3M cutoff mismatch


def test_leg_cutoff_mismatch_flags_warning_and_uses_later_publication():
    vix = _parse_vix(_read("synthetic_vix_close.csv"))
    vix3m = parse_risk_stress_csv(
        _read("synthetic_vix3m_delayed_publication.csv"),
        series=VIX3M_LEG,
        provider="cboe",
        origin="FIXTURE",
    )
    points = compute_vix_term_structure(vix, vix3m)
    mismatched = [p for p in points if "cutoff_mismatch" in p.warnings]
    assert mismatched, "legs with different available_at must be flagged"
    for point in mismatched:
        vix_row = next(r for r in vix if r.observation_date == point.observation_date)
        vix3m_row = next(r for r in vix3m if r.observation_date == point.observation_date)
        assert point.available_at == max(vix_row.available_at, vix3m_row.available_at)
    # The 2026-01-08 ratio must not appear before its slower leg publishes.
    late = next(p for p in points if p.observation_date == date(2026, 1, 8))
    assert late.available_at == datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 4. stale source


def test_stale_source_is_reported_not_hidden():
    records = _parse_vix(_read("synthetic_vix_close.csv"))
    state = evaluate_series_state(
        records, decision_time=datetime(2026, 2, 20, tzinfo=UTC)
    )
    assert state["status"] == SourceStatus.STALE
    assert any(w.startswith("stale_latest_observation_age_days") for w in state["warnings"])
    fresh = evaluate_series_state(records, decision_time=DECISION_TIME)
    assert fresh["status"] == SourceStatus.OK


def test_staleness_threshold_is_respected_exactly():
    records = _parse_vix(_read("synthetic_vix_close.csv"))
    state = evaluate_series_state(
        records,
        decision_time=datetime(2026, 1, 16, tzinfo=UTC),
    )
    assert state["status"] == SourceStatus.OK


# ---------------------------------------------------------------------------
# 5. unapproved source


def test_unapproved_provider_source_pair_is_rejected():
    with pytest.raises(UnapprovedSourceError):
        parse_risk_stress_csv(
            _read("synthetic_vix_close.csv"),
            series=RiskStressSeries.VIX_LEVEL,
            provider="random_blog_scraper",
            origin="FIXTURE",
        )


def test_unapproved_source_series_id_is_rejected():
    swapped = _read("synthetic_baa10y.csv")
    with pytest.raises(UnapprovedSourceError):
        parse_risk_stress_csv(
            swapped, series=RiskStressSeries.HY_OAS, provider="fred", origin="FIXTURE"
        )


# ---------------------------------------------------------------------------
# 6. available_at > decision_time


def test_future_publication_never_enters_decision():
    vix3m = parse_risk_stress_csv(
        _read("synthetic_vix3m_delayed_publication.csv"),
        series=VIX3M_LEG,
        provider="cboe",
        origin="FIXTURE",
    )
    admissible = asof_records(vix3m, DECISION_TIME)
    assert all(r.available_at <= DECISION_TIME for r in admissible)
    assert len(admissible) == 3
    assert {r.observation_date for r in admissible} == {
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    }


def test_naive_available_at_is_rejected_not_localized_silently():
    text = _read("synthetic_vix_close.csv").replace("+00:00", "")
    with pytest.raises(RiskStressError, match="explicit_utc_offset"):
        _parse_vix(text)


# ---------------------------------------------------------------------------
# 7. HY OAS historical truncation representation


def test_hy_oas_truncated_history_is_flagged_not_spliced():
    records = parse_risk_stress_csv(
        _read("synthetic_hy_oas_truncated.csv"),
        series=RiskStressSeries.HY_OAS,
        provider="fred",
        origin="FIXTURE",
    )
    contract = source_contract(RiskStressSeries.HY_OAS)
    state = evaluate_series_state(
        records,
        decision_time=datetime(2024, 3, 10, tzinfo=UTC),
        expected_history_start=contract.expected_history_start,
    )
    assert state["status"] == SourceStatus.OK
    assert any(w.startswith("history_truncated") for w in state["warnings"])
    assert state["coverage_start"] == date(2024, 3, 1)


def test_hy_oas_partial_null_values_are_reported():
    truncated = _read("synthetic_hy_oas_truncated.csv").replace("3.51", "")
    with pytest.raises(RiskStressError, match="missing_value"):
        parse_risk_stress_csv(
            truncated, series=RiskStressSeries.HY_OAS, provider="fred", origin="FIXTURE"
        )
    # A null-valued but well-formed row is representable and yields PARTIAL.
    padded = _read("synthetic_hy_oas_truncated.csv").replace("3.51", "NaN")
    records = parse_risk_stress_csv(
        padded, series=RiskStressSeries.HY_OAS, provider="fred", origin="FIXTURE"
    )
    assert records[1].value is None
    state = evaluate_series_state(
        records, decision_time=datetime(2024, 3, 10, tzinfo=UTC)
    )
    assert state["status"] == SourceStatus.PARTIAL


# ---------------------------------------------------------------------------
# 8. BAA10Y / HY OAS semantic isolation


def test_baa10y_contract_is_shadow_proxy_and_distinct_from_hy_oas():
    hy = source_contract(RiskStressSeries.HY_OAS)
    baa = source_contract(RiskStressSeries.BAA10Y)
    assert baa.role == SourceRole.SHADOW_PROXY
    assert hy.role == SourceRole.PRIMARY
    assert baa.approved_sources != hy.approved_sources
    assert baa.series != hy.series
    assert "!= RISK_HY_OAS" in baa.notes
    assert "No historical splice" in baa.notes
    # No shared absolute-threshold machinery exists on either contract.
    assert not hasattr(baa, "thresholds") and not hasattr(hy, "thresholds")


def test_baa_rows_cannot_be_spliced_into_hy_oas_series():
    baa_records = parse_risk_stress_csv(
        _read("synthetic_baa10y.csv"),
        series=RiskStressSeries.BAA10Y,
        provider="fred",
        origin="FIXTURE",
    )
    with pytest.raises(SpliceViolationError):
        check_series_identity(baa_records, RiskStressSeries.HY_OAS)
    check_series_identity(baa_records, RiskStressSeries.BAA10Y)


def test_baa10y_uses_its_own_absolute_levels_not_hy_thresholds():
    # Direction-confirmation semantics only: the two series keep separate
    # value scales and neither maps onto the other's bands.
    baa_records = parse_risk_stress_csv(
        _read("synthetic_baa10y.csv"),
        series=RiskStressSeries.BAA10Y,
        provider="fred",
        origin="FIXTURE",
    )
    hy_records = parse_risk_stress_csv(
        _read("synthetic_hy_oas_truncated.csv"),
        series=RiskStressSeries.HY_OAS,
        provider="fred",
        origin="FIXTURE",
    )
    assert {r.source_series_id for r in baa_records} == {"BAA10Y"}
    assert {r.source_series_id for r in hy_records} == {"BAMLH0A0HYM2"}


# ---------------------------------------------------------------------------
# 9. malformed input


def test_malformed_fixture_rows_raise_with_line_context():
    text = _read("synthetic_malformed.csv")
    with pytest.raises(RiskStressError, match="line_3_invalid_observation_date"):
        _parse_vix(text)
    numeric_bad = text.replace("not-a-date", "2026-01-06").replace("not-a-number", "oops")
    with pytest.raises(RiskStressError, match="line_4_non_numeric_value"):
        _parse_vix(numeric_bad)
    missing_avail = _read("synthetic_vix_close.csv").replace(
        "2026-01-07T04:15:00+00:00", ""
    )
    with pytest.raises(RiskStressError, match="missing_available_at"):
        _parse_vix(missing_avail)


def test_header_and_column_contract_is_enforced():
    with pytest.raises(RiskStressError, match="empty_csv"):
        _parse_vix("")
    with pytest.raises(RiskStressError, match="missing_required_columns"):
        _parse_vix("observation_date,value\n2026-01-05,18.21\n")
    with pytest.raises(RiskStressError, match="origin"):
        parse_risk_stress_csv(
            _read("synthetic_vix_close.csv"),
            series=RiskStressSeries.VIX_LEVEL,
            provider="cboe",
            origin="YOUTUBE_COMMENT",
        )


# ---------------------------------------------------------------------------
# 10. fixture / live separation


def test_every_synthetic_fixture_declares_fixture_origin_in_records():
    for name, series, provider in (
        ("synthetic_vix_close.csv", RiskStressSeries.VIX_LEVEL, "cboe"),
        ("synthetic_vix3m_close.csv", VIX3M_LEG, "cboe"),
        ("synthetic_hy_oas_truncated.csv", RiskStressSeries.HY_OAS, "fred"),
        ("synthetic_baa10y.csv", RiskStressSeries.BAA10Y, "fred"),
    ):
        records = parse_risk_stress_csv(
            _read(name), series=series, provider=provider, origin="FIXTURE"
        )
        assert records, f"{name} must parse"
        assert all(r.origin == "FIXTURE" for r in records)
        assert all(r.metadata["origin"] == "FIXTURE" for r in records)


def test_origin_label_is_explicit_and_recorded(tmp_path):
    records = _parse_vix(_read("synthetic_vix_close.csv"))
    assert all(r.metadata["parser_version"] == PARSER_VERSION for r in records)
    live_label = parse_risk_stress_csv(
        _read("synthetic_vix_close.csv"),
        series=RiskStressSeries.VIX_LEVEL,
        provider="cboe",
        origin="LIVE",
    )
    assert all(r.origin == "LIVE" for r in live_label)
    assert {r.origin for r in records} == {"FIXTURE"}


# ---------------------------------------------------------------------------
# source health / raw archive plumbing


def test_source_health_captures_raw_hash_parser_version_and_state(tmp_path):
    archive = ImmutableRawArchive(root=tmp_path / "raw")
    fetched_at = datetime(2026, 1, 10, tzinfo=UTC)
    health = ingest_source_snapshot(
        _read("synthetic_vix_close.csv"),
        series=RiskStressSeries.VIX_LEVEL,
        provider="cboe",
        origin="FIXTURE",
        fetched_at=fetched_at,
        decision_time=DECISION_TIME,
        raw_archive=archive,
    )
    assert health.status == SourceStatus.OK
    assert health.parser_version == PARSER_VERSION
    assert health.raw_sha256
    assert health.raw_archive_path and Path(health.raw_archive_path).exists()
    assert health.row_count == 5
    assert health.coverage_start == date(2026, 1, 5)
    assert health.coverage_end == date(2026, 1, 9)
    assert health.latest_observation_date == date(2026, 1, 9)
    assert health.latest_available_at == datetime(2026, 1, 10, 4, 15, tzinfo=UTC)
    assert health.failure_reason is None
    as_dict = health.as_dict()
    assert as_dict["raw_sha256"] == health.raw_sha256


def test_source_health_preserves_failure_reason_for_malformed_snapshot(tmp_path):
    health = ingest_source_snapshot(
        _read("synthetic_malformed.csv"),
        series=RiskStressSeries.VIX_LEVEL,
        provider="cboe",
        origin="FIXTURE",
        fetched_at=DECISION_TIME,
        decision_time=DECISION_TIME,
    )
    assert health.status == SourceStatus.FAILED
    assert health.failure_reason and "invalid_observation_date" in health.failure_reason
    assert health.row_count == 0


def test_term_structure_semantics_band_labels_only():
    assert classify_term_structure(0.9) == "CONTANGO_NORMAL"
    assert classify_term_structure(1.0) == "FLAT"
    assert classify_term_structure(1.1) == "BACKWARDATION_STRESS"
    # Research knob, not a production threshold claim.
    assert classify_term_structure(1.02, flat_tolerance=0.05) == "FLAT"
    with pytest.raises(ValueError):
        classify_term_structure(1.0, flat_tolerance=-0.1)


def test_vix_ts_has_no_direct_source_contract():
    with pytest.raises(ValueError, match="derived"):
        source_contract(RiskStressSeries.VIX_TS)
    leg = vix3m_contract()
    assert ("cboe", "VIX3M") in leg.approved_sources
