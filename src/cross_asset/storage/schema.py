"""DuckDB schema for the point-in-time data store."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS series_catalog (
 series_id VARCHAR PRIMARY KEY, display_name VARCHAR NOT NULL, asset_class VARCHAR,
 category VARCHAR, frequency VARCHAR NOT NULL, unit VARCHAR NOT NULL, currency VARCHAR,
 timezone VARCHAR, critical BOOLEAN NOT NULL DEFAULT FALSE, point_in_time_class VARCHAR NOT NULL,
 stale_after_hours DOUBLE, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP NOT NULL,
 updated_at TIMESTAMP NOT NULL);
CREATE TABLE IF NOT EXISTS source_mapping (
 series_id VARCHAR NOT NULL, provider VARCHAR NOT NULL, source_series_id VARCHAR NOT NULL,
 priority INTEGER NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE,
 semantic_equivalence BOOLEAN NOT NULL DEFAULT TRUE, adjustment VARCHAR, notes VARCHAR,
 PRIMARY KEY(series_id, provider, source_series_id));
CREATE TABLE IF NOT EXISTS observations (
 series_id VARCHAR NOT NULL, observation_date DATE NOT NULL, available_at TIMESTAMP NOT NULL,
 value DOUBLE, source VARCHAR NOT NULL, source_series_id VARCHAR NOT NULL, vintage_date DATE,
 ingested_at TIMESTAMP NOT NULL, quality VARCHAR NOT NULL DEFAULT 'ok', raw_file VARCHAR,
 run_id VARCHAR NOT NULL, PRIMARY KEY(series_id, observation_date, available_at, source, source_series_id));
CREATE TABLE IF NOT EXISTS ingestion_runs (
 run_id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, started_at TIMESTAMP NOT NULL,
 finished_at TIMESTAMP, status VARCHAR NOT NULL, requested_series INTEGER,
 success_series INTEGER, failed_series INTEGER, rows_written BIGINT, error_summary VARCHAR);
CREATE TABLE IF NOT EXISTS provider_attempts (
 attempt_id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, series_id VARCHAR NOT NULL,
 started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP, status VARCHAR NOT NULL,
 latency_ms DOUBLE, schema_error VARCHAR, fallback BOOLEAN NOT NULL DEFAULT FALSE,
 source_switch BOOLEAN NOT NULL DEFAULT FALSE, error_message VARCHAR);
CREATE TABLE IF NOT EXISTS data_quality_events (
 event_id VARCHAR PRIMARY KEY, detected_at TIMESTAMP NOT NULL, series_id VARCHAR NOT NULL,
 severity VARCHAR NOT NULL, event_type VARCHAR NOT NULL, message VARCHAR NOT NULL,
 provider VARCHAR, run_id VARCHAR);
CREATE TABLE IF NOT EXISTS factor_values (
 as_of TIMESTAMP NOT NULL, factor_id VARCHAR NOT NULL, entity_id VARCHAR NOT NULL,
 raw_value DOUBLE, score DOUBLE, confidence DOUBLE, model_version VARCHAR NOT NULL,
 data_cutoff TIMESTAMP NOT NULL, created_at TIMESTAMP NOT NULL,
 PRIMARY KEY(as_of, factor_id, entity_id, model_version));
CREATE TABLE IF NOT EXISTS asset_scores (
 as_of TIMESTAMP NOT NULL, asset_id VARCHAR NOT NULL, macro_score DOUBLE, trend_score DOUBLE,
 valuation_score DOUBLE, carry_score DOUBLE, risk_score DOUBLE, structure_score DOUBLE,
 total_score DOUBLE, confidence DOUBLE, model_version VARCHAR NOT NULL, data_cutoff TIMESTAMP NOT NULL,
 created_at TIMESTAMP NOT NULL, PRIMARY KEY(as_of, asset_id, model_version));
CREATE TABLE IF NOT EXISTS data_snapshots (
 snapshot_id VARCHAR PRIMARY KEY, created_at TIMESTAMP NOT NULL,
 series_count BIGINT NOT NULL DEFAULT 0, observation_count BIGINT NOT NULL DEFAULT 0,
 max_available_at TIMESTAMP, data_cutoff TIMESTAMP, manifest_hash VARCHAR NOT NULL,
 manifest_json VARCHAR NOT NULL DEFAULT '{}', config_hash VARCHAR);
CREATE TABLE IF NOT EXISTS model_runs (
 run_id VARCHAR PRIMARY KEY, run_type VARCHAR NOT NULL, decision_time TIMESTAMP,
 model_version VARCHAR NOT NULL, config_hash VARCHAR NOT NULL, code_version VARCHAR NOT NULL,
 data_snapshot_id VARCHAR, data_cutoff TIMESTAMP, status VARCHAR NOT NULL,
 warnings VARCHAR NOT NULL DEFAULT '[]', started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS data_acceptance_registry (
 series_id VARCHAR NOT NULL, provider VARCHAR NOT NULL, source_series_id VARCHAR NOT NULL,
 status VARCHAR NOT NULL, tech_gate VARCHAR NOT NULL, legal_gate VARCHAR NOT NULL,
 pit_gate VARCHAR NOT NULL, stability_gate VARCHAR NOT NULL, pit_grade VARCHAR,
 origin VARCHAR NOT NULL, permission_scope VARCHAR, semantic_equivalence BOOLEAN,
 manifest_hash VARCHAR, reviewer VARCHAR, approved_at TIMESTAMP, evidence_json VARCHAR NOT NULL DEFAULT '{}',
 updated_at TIMESTAMP NOT NULL, usage_status VARCHAR DEFAULT 'EVIDENCE_ONLY', PRIMARY KEY(series_id, provider, source_series_id));
"""


def initialize_schema(connection):
    """Create all tables atomically and return the connection."""
    connection.execute("BEGIN")
    try:
        connection.execute(SCHEMA_SQL)
        # Additive migrations for databases created by earlier waves.
        for statement in (
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS series_count BIGINT DEFAULT 0",
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS observation_count BIGINT DEFAULT 0",
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS max_available_at TIMESTAMP",
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS data_cutoff TIMESTAMP",
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS manifest_hash VARCHAR",
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS manifest_json VARCHAR DEFAULT '{}'",
            "ALTER TABLE data_snapshots ADD COLUMN IF NOT EXISTS config_hash VARCHAR",
            "ALTER TABLE data_acceptance_registry ADD COLUMN IF NOT EXISTS usage_status VARCHAR",
        ):
            connection.execute(statement)
        connection.execute("UPDATE data_acceptance_registry SET usage_status='EVIDENCE_ONLY' WHERE usage_status IS NULL")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return connection


init_schema = initialize_schema
