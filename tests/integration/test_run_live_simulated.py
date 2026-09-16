from datetime import UTC, datetime, timedelta

import pytest

from cross_asset.domain.models import Observation
from cross_asset.ingestion.live_run import run_live_pipeline
from cross_asset.storage import init_db


def test_simulated_live_vertical_slice_idempotency_and_failure(tmp_path):
    store=init_db(':memory:')
    start=datetime(2025,1,1,tzinfo=UTC)
    def fetch(series):
        return [Observation(series_id=s, observation_date=(start+timedelta(days=i)).date(), available_at=start+timedelta(days=40), value=100+i, source='simulated', source_series_id=s, frequency='daily', unit='fixture') for s in series for i in range(30)]
    first=run_live_pipeline(store=store,archive_root=tmp_path/'raw',output_root=tmp_path/'out',fetcher=fetch)
    assert first['status']=='SIMULATED_SUCCESS' and first['series_count']==8 and set(first['source_mode'].values())=={'SIMULATED'}
    assert len(list((tmp_path/'raw').rglob('*'))) > 0
    assert store.conn.execute('select count(distinct series_id) from observations').fetchone()[0]==8
    assert store.conn.execute('select count(*) from provider_attempts').fetchone()[0]==8
    assert store.conn.execute('select count(*) from data_snapshots').fetchone()[0]==1
    assert store.conn.execute('select status from model_runs').fetchone()[0]=='success'
    assert len(list((tmp_path/'out').rglob('*.json'))) + len(list((tmp_path/'out').rglob('*.md'))) == 9
    assert run_live_pipeline(store=store,archive_root=tmp_path/'raw',output_root=tmp_path/'out',fetcher=fetch)['reused'] is True
    retry=run_live_pipeline(store=store,archive_root=tmp_path/'raw',output_root=tmp_path/'out',fetcher=fetch,retry=True)
    assert retry['run_key'] != first['run_key'] and retry['status']=='SIMULATED_SUCCESS'
    def fail(_): raise RuntimeError('simulated provider failure')
    bad=run_live_pipeline(store=init_db(':memory:'),archive_root=tmp_path/'raw2',output_root=tmp_path/'out2',fetcher=fail)
    assert bad['status']=='DEGRADED' and set(bad['source_mode'].values())=={'UNAVAILABLE'}


def test_fixture_mode_writes_with_fixture_source_identity(tmp_path):
    store=init_db(':memory:')
    start=datetime(2025,1,1,tzinfo=UTC)
    def fetch(series):
        return [Observation(series_id=s, observation_date=(start+timedelta(days=i)).date(), available_at=start+timedelta(days=40), value=100+i, source='fixture', source_series_id=s, frequency='daily', unit='fixture') for s in series for i in range(30)]

    result=run_live_pipeline(
        store=store,
        archive_root=tmp_path/'fixture-raw',
        output_root=tmp_path/'fixture-out',
        fetcher=fetch,
        source_mode='FIXTURE',
    )

    assert result['status']=='SIMULATED_SUCCESS'
    assert result['series_count']==8
    assert set(result['source_mode'].values())=={'FIXTURE'}
    assert store.conn.execute('select count(*) from observations').fetchone()[0] == 240


@pytest.mark.parametrize('source_mode', ['SIMULATED', 'FIXTURE'])
def test_synthetic_modes_reject_real_source_identity_before_persistence(tmp_path, source_mode):
    store=init_db(':memory:')
    start=datetime(2025,1,1,tzinfo=UTC)
    raw_root=tmp_path/f'guard-raw-{source_mode.lower()}'
    def fetch(series):
        return [Observation(series_id=series[0], observation_date=start.date(), available_at=start, value=100, source='manual', source_series_id='SPX', frequency='daily', unit='index')]

    with pytest.raises(
        ValueError,
        match=f'synthetic_source_identity_required:{source_mode.lower()}:US_EQ:manual',
    ):
        run_live_pipeline(
            store=store,
            archive_root=raw_root,
            output_root=tmp_path/f'guard-out-{source_mode.lower()}',
            fetcher=fetch,
            source_mode=source_mode,
        )

    assert store.conn.execute('select count(*) from observations').fetchone()[0] == 0
    assert not raw_root.exists()
