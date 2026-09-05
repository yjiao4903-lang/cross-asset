"""Shared fixtures/helpers for approved-provenance test scenarios.

Registry rows and calendar configs produced here only prove gate mechanics
inside ephemeral test databases. They never represent a real acceptance
decision, a real Wind entitlement, or real calendar evidence (Issue #18/#21).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def approve_test_series(
    store,
    *,
    series_ids,
    provider,
    source_series_id=None,
    usage_status="LIVE_VERIFIED",
    origin="LIVE",
    approved_at=datetime(2026, 1, 1, tzinfo=UTC),
):
    """Register fabricated PASS provenance rows matching the seeded observations."""

    for series_id in series_ids:
        upsert_data_acceptance(
            store,
            {
                "series_id": series_id,
                "provider": provider,
                "source_series_id": source_series_id or series_id,
                "status": "PASS",
                "tech_gate": "PASS",
                "legal_gate": "PASS",
                "pit_gate": "PASS",
                "stability_gate": "PASS",
                "pit_grade": "B",
                "origin": origin,
                "permission_scope": "test",
                "semantic_equivalence": True,
                "manifest_hash": f"manifest-{series_id}",
                "reviewer": "test-reviewer",
                "approved_at": approved_at,
                "evidence_json": "{}",
                "updated_at": approved_at,
                "usage_status": usage_status,
            },
        )


def write_test_calendar_configs(
    tmp_path,
    *,
    series_ids,
    calendar="TEST",
    max_lag_sessions=15,
    covered_years=(2026,),
):
    """Write a VERIFIED test calendar and explicit per-series lag budgets."""

    calendars = {
        calendar: {
            "calendar_id": calendar,
            "capability_status": "VERIFIED",
            "timezone": "UTC",
            "source": "test-fixture",
            "source_version": "1",
            "version": "1",
            "covered_years": list(covered_years),
            "open_time": "00:00",
            "close_time": "23:59",
            "regular_close": "23:59",
            "holidays": [],
            "early_closes": {},
            "verified": True,
            "evidence": ["test fixture calendar; not real exchange evidence"],
            "reviewer": "test-reviewer",
            "approved_at": "2026-01-01T00:00:00+00:00",
        }
    }
    calendar_path = Path(tmp_path) / "calendars.yml"
    calendar_path.write_text(
        yaml.safe_dump({"calendars": calendars}), encoding="utf-8"
    )
    mapping_path = Path(tmp_path) / "series_calendars.yml"
    mapping_path.write_text(
        yaml.safe_dump(
            {
                "series_calendars": {
                    series_id: {
                        "calendar": calendar,
                        "max_lag_sessions": max_lag_sessions,
                    }
                    for series_id in series_ids
                }
            }
        ),
        encoding="utf-8",
    )
    return calendar_path, mapping_path
