from datetime import datetime

from cross_asset.research.protocol import ResearchProtocol
from cross_asset.research.readiness import evaluate_research_readiness
from cross_asset.storage import init_db

from .test_protocol_plan import RAW


def test_readiness_blocks_empty_formal_store():
    store = init_db(":memory:")
    try:
        store.conn.execute(
            """INSERT INTO series_catalog
               (series_id,display_name,frequency,unit,critical,point_in_time_class,created_at,updated_at)
               VALUES ('A','A','daily','price',TRUE,'market',?,?)""",
            [datetime(2026, 1, 1), datetime(2026, 1, 1)],
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
