from datetime import UTC, datetime, timedelta

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
