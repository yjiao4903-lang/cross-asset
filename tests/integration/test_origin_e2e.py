from datetime import UTC, date, datetime

from cross_asset.domain.models import DataRequest, Observation
from cross_asset.ingestion import IngestionRunner
from cross_asset.ingestion.live_run import run_live_pipeline
from cross_asset.ingestion.origin import (
    DataOrigin,
    OriginEvidence,
    summarize_origins,
    validate_origin_evidence,
)
from cross_asset.providers.manual import ManualProvider
from cross_asset.storage import init_db


def test_manual_provider_runner_raw_db_origin(tmp_path):
    f=tmp_path/'m.csv'; f.write_text('series_id,observation_date,value,available_at\nS,2025-01-01,1,2025-01-02T00:00:00+00:00')
    p=ManualProvider(path=str(f),template_id='t'); store=init_db(':memory:'); result=IngestionRunner(store).run(p,p.fetch,DataRequest(series_ids=['S']))
    assert result['status']=='success'; row=store.conn.execute('select quality from observations').fetchone(); assert row
    assert p.fetch(DataRequest(series_ids=['S']))[0].metadata['origin']=='MANUAL'

def test_manual_missing_available_at_rejected(tmp_path):
    f=tmp_path/'m.csv'; f.write_text('series_id,observation_date,value\nS,2025-01-01,1')
    provider=ManualProvider(path=str(f)); assert provider.fetch(DataRequest(series_ids=['S']))==[]
    assert provider.last_error and provider.last_error['code']=='schema_error'

def test_simulated_main_path_artifacts_origin(tmp_path):
    def fetch(series): return [Observation(series_id=s, observation_date=date(2025,1,1), available_at=datetime(2025,1,2,tzinfo=UTC), value=i+1, source='simulated', source_series_id=s, frequency='daily', unit='fixture') for i,s in enumerate(series)]
    store=init_db(':memory:'); out=run_live_pipeline(store=store,archive_root=tmp_path/'raw',output_root=tmp_path/'out',fetcher=fetch,source_mode='SIMULATED',as_of=datetime(2025,1,3,tzinfo=UTC),lock_path=tmp_path/'lock')
    assert out['run_mode']=='LIVE' and out['status']=='SIMULATED_SUCCESS' and out['origin_summary']['origin']=='SIMULATED' and out['series_count']==8
    assert (tmp_path/'out/2025-01-03/run_manifest.json').exists()
    assert len(list((tmp_path/'raw').rglob('*.json')))==1
    assert {r[0] for r in store.conn.execute('select distinct series_id from observations').fetchall()}=={'US_EQ','GOLD','COPPER','OIL','DXY','USDCNH','HK_EQ','US_GOV_10Y'}
    assert store.conn.execute('select count(*) from provider_attempts').fetchone()[0]==8
    assert store.conn.execute('select count(*) from data_snapshots').fetchone()[0]==1
    assert store.conn.execute('select count(*) from model_runs').fetchone()[0]==1
    assert len(list((tmp_path/'out/2025-01-03').glob('*')))==9

def test_fake_live_evidence_rejected():
    ok, errors=validate_origin_evidence(OriginEvidence(DataOrigin.LIVE,provider='x')); assert not ok and errors

def test_mixed_and_legacy_are_not_live():
    summary=summarize_origins([{'metadata':{'origin':'MANUAL'}},{'metadata':{'origin':'SIMULATED'}},{'metadata':{}}]); assert summary['mixed'] and summary['counts']['UNAVAILABLE']==1
