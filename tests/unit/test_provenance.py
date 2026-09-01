from datetime import UTC, date, datetime

import duckdb
import pytest

from cross_asset.storage.provenance import ProvenanceStore, config_hash
from cross_asset.storage.schema import initialize_schema


def _row(value=1):
    return {'series_id': 'US_EQ', 'source': 'fixture', 'available_at': datetime(2025, 1, 2, tzinfo=UTC), 'observation_date': date(2025, 1, 1), 'value': value}


def test_snapshot_config_hash_is_persisted_and_stable(tmp_path):
    cfg = tmp_path / 'config.yml'; cfg.write_text('alpha: 1\n', encoding='utf-8')
    h = config_hash([cfg]); conn = initialize_schema(duckdb.connect(':memory:')); p = ProvenanceStore(conn)
    sid = p.create_snapshot([_row()], config_hash_value=h)
    assert conn.execute('select config_hash from data_snapshots where snapshot_id=?', [sid]).fetchone()[0] == h
    assert sid == p.create_snapshot([_row()], config_hash_value=h)


def test_config_hash_changes_with_config_and_rejects_missing(tmp_path):
    cfg = tmp_path / 'config.yml'; cfg.write_text('alpha: 1\n', encoding='utf-8'); first = config_hash([cfg])
    cfg.write_text('alpha: 2\n', encoding='utf-8'); assert first != config_hash([cfg])
    p = ProvenanceStore(initialize_schema(duckdb.connect(':memory:')))
    with pytest.raises(ValueError): p.start_model_run('test', None, 'v1', '', 'no-commit', None)


def test_old_snapshot_schema_gets_additive_config_hash_migration():
    conn = duckdb.connect(':memory:')
    conn.execute("create table data_snapshots (snapshot_id varchar primary key, created_at timestamp, manifest_hash varchar, manifest_json varchar)")
    initialize_schema(conn)
    cols = {r[0] for r in conn.execute("describe data_snapshots").fetchall()}
    assert 'config_hash' in cols
