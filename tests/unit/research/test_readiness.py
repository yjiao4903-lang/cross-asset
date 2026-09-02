import json
from datetime import UTC, datetime

import pandas as pd

from cross_asset.research.protocol import ResearchProtocol
from cross_asset.research.readiness import evaluate_research_readiness
from cross_asset.storage import init_db

RAW = {
    "version": "0.3",
    "status": "PLANNING_ONLY",
    "owner": "TBD",
    "reviewer": "TBD",
    "approved_at": "TBD",
    "windows": {
        "default_mode": "expanding",
        "train_min_years": 5,
        "test_window_months": 12,
        "step_months": 3,
        "rolling_years": None,
        "final_holdout": "last_20_percent",
    },
    "coverage_threshold": 0.95,
    "rebalance": "weekly",
    "transaction_cost_bps": [0, 5, 10, 20, 30],
    "base_cost_bps": 10,
    "turnover_convention": "two_sided_notional",
    "charge_initial_trade": False,
    "signal_model_version": "full_model_v0.2",
    "benchmarks": ["STATIC", "TREND_ONLY", "MACRO_ONLY", "RISK_ONLY", "FULL_MODEL"],
    "execution": {
        "require_protocol_status": "FROZEN",
        "holdout_release": False,
        "required_registry_status": "PASS",
        "required_usage_status": "RESEARCH_ADMISSIBLE",
        "require_all_critical_series": True,
    },
    "evaluation_thresholds": {
        "min_oos_observations": 52,
        "min_information_ratio_vs_static": 0.0,
        "min_annualized_excess_return_vs_static": 0.0,
        "max_drawdown_penalty_vs_static": 0.05,
    },
    "data_policy": {
        "project_status": "REAL_DATA_ADMISSION",
        "zero_imputation": False,
        "decision_cutoff": "available_at <= decision_time",
        "revision_policy": "latest_released_revision_per_observation_date",
    },
}


def test_readiness_blocks_empty_formal_store():
    store = init_db(":memory:")
    try:
        store.conn.execute(
            """INSERT INTO series_catalog
               (series_id,display_name,frequency,unit,critical,point_in_time_class,created_at,updated_at)
               VALUES ('A','A','daily','price',TRUE,'market',?,?)""",
            [datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)],
        )
        result = evaluate_research_readiness(
            store.conn,
            ResearchProtocol.from_mapping(RAW),
        )
        assert result["status"] == "BLOCKED"
        assert "formal_observations_empty" in result["blockers"]
        assert any("registry_pass_research_admissible_required" in item for item in result["blockers"])
    finally:
        store.close()



def _frozen_protocol():
    raw = json.loads(json.dumps(RAW))
    raw.update(
        {
            "status": "FROZEN",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-09-02T10:00:00+08:00",
        }
    )
    return ResearchProtocol.from_mapping(raw)


def test_readiness_enforces_pit_freshness_coverage_threshold():
    store = init_db(":memory:")
    try:
        now = datetime(2026, 9, 2, tzinfo=UTC)
        store.conn.execute(
            """INSERT INTO series_catalog
               (series_id,display_name,frequency,unit,critical,point_in_time_class,
                stale_after_hours,created_at,updated_at)
               VALUES ('A','A','weekly','price',TRUE,'market',96,?,?)""",
            [now, now],
        )
        store.conn.execute(
            """INSERT INTO data_acceptance_registry
               (series_id,provider,source_series_id,status,tech_gate,legal_gate,pit_gate,
                stability_gate,pit_grade,origin,permission_scope,semantic_equivalence,
                manifest_hash,reviewer,approved_at,evidence_json,updated_at,usage_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                "A",
                "manual",
                "A",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "PASS",
                "B",
                "MANUAL",
                "research",
                True,
                "hash",
                "reviewer",
                now,
                "{}",
                now,
                "RESEARCH_ADMISSIBLE",
            ],
        )

        decisions = pd.date_range(
            "2026-01-02T16:00:00Z",
            periods=20,
            freq="W-FRI",
        )
        observations = [
            {
                "series_id": "A",
                "observation_date": datetime(2018, 1, 5, tzinfo=UTC).date(),
                "available_at": datetime(2018, 1, 5, 16, tzinfo=UTC),
                "value": 90.0,
                "source": "manual",
                "source_series_id": "A",
                "vintage_date": None,
                "ingested_at": now,
                "quality": "ok",
                "raw_file": "fixture",
            }
        ]
        missing_indices = {5, 15}
        for index, decision in enumerate(decisions):
            if index in missing_indices:
                continue
            observations.append(
                {
                    "series_id": "A",
                    "observation_date": decision.date(),
                    "available_at": decision.to_pydatetime(),
                    "value": 100.0 + index,
                    "source": "manual",
                    "source_series_id": "A",
                    "vintage_date": None,
                    "ingested_at": now,
                    "quality": "ok",
                    "raw_file": "fixture",
                }
            )
        store.insert_observations(observations, run_id="coverage-fixture")

        blocked = evaluate_research_readiness(
            store.conn,
            _frozen_protocol(),
            decision_times=decisions,
        )
        assert blocked["status"] == "BLOCKED"
        assert blocked["series"][0]["pit_coverage"]["coverage"] == 0.9
        assert any("pit_coverage_below_threshold" in item for item in blocked["blockers"])

        fill_rows = []
        for index in sorted(missing_indices):
            decision = decisions[index]
            fill_rows.append(
                {
                    "series_id": "A",
                    "observation_date": decision.date(),
                    "available_at": decision.to_pydatetime(),
                    "value": 100.0 + index,
                    "source": "manual",
                    "source_series_id": "A",
                    "vintage_date": None,
                    "ingested_at": now,
                    "quality": "ok",
                    "raw_file": "fixture",
                }
            )
        store.insert_observations(fill_rows, run_id="coverage-fill")

        ready = evaluate_research_readiness(
            store.conn,
            _frozen_protocol(),
            decision_times=decisions,
        )
        assert ready["status"] == "READY_FOR_OOS"
        assert ready["series"][0]["pit_coverage"]["coverage"] == 1.0
    finally:
        store.close()
