from datetime import UTC, date, datetime, timedelta

import pytest

from cross_asset.domain.models import Observation
from cross_asset.live.locks import RunLock
from cross_asset.operations.shadow import ShadowRunner, load_schedule
from cross_asset.storage import init_db


def make_runner(tmp_path, fail_on=None, stale_on=None):
    calls={'n':0}
    def fetch(series, as_of):
        calls['n']+=1
        if calls['n']==fail_on: raise RuntimeError('provider down')
        quality='stale' if calls['n']==stale_on else 'ok'
        end=as_of.date() if hasattr(as_of, 'date') else as_of
        rows=[]
        for s in series:
            # A real-looking 30-day history makes the model's trend component
            # observable while keeping every vintage available at decision time.
            phase=(calls['n'] + sum(ord(c) for c in s)) % 7 - 3
            slope=phase / 100
            for i in range(30):
                obs_day=end-timedelta(days=29-i)
                rows.append(Observation(series_id=s, observation_date=obs_day, available_at=datetime(obs_day.year, obs_day.month, obs_day.day, tzinfo=UTC), value=100+slope*i+calls['n'], source='simulated', source_series_id=s, frequency='daily', unit='fixture', quality=quality))
        return rows
    return ShadowRunner(init_db(':memory:'),tmp_path/'raw',tmp_path/'out',fetcher=fetch,lock_path=tmp_path/'lock')

def test_seven_dates_success_and_changes(tmp_path):
    r=make_runner(tmp_path); ds=[date(2025,1,1)+timedelta(days=i) for i in range(7)]; out=[r.run(d) for d in ds]
    assert len(out)==7 and all(x['run_mode']=='SHADOW' for x in out)
    scores=[]; weights=[]
    for d in ds:
        root=tmp_path/'out'/d.isoformat()
        score=__import__('json').loads((root/'asset_scores.json').read_text())['scores']['US_EQ']
        confidence=__import__('json').loads((root/'asset_scores.json').read_text())['confidence']['US_EQ']
        scores.append(score); weights.append(__import__('json').loads((root/'allocation.json').read_text())['weights'])
        assert score is not None and confidence is not None
    assert len({str(s) for s in scores}) >= 2
    assert len({str(w) for w in weights}) >= 2

def test_provider_exception_degraded_and_db_recorded(tmp_path):
    r=make_runner(tmp_path,3); out=[r.run(date(2025,1,1)+timedelta(days=i)) for i in range(3)]; assert out[-1]['status']=='DEGRADED'; assert r.store.conn.execute("select count(*) from provider_attempts where status='FAILED'").fetchone()[0]==8

def test_critical_stale_freezes_allocation_and_recovers(tmp_path):
    r=make_runner(tmp_path,stale_on=2); assert r.run(date(2025,1,1))['status']=='SIMULATED_SUCCESS'; assert r.run(date(2025,1,2))['allocation_status']=='FROZEN'; assert r.run(date(2025,1,3))['status']=='SIMULATED_SUCCESS'

def test_idempotency_and_retry_keys(tmp_path):
    r=make_runner(tmp_path); a=r.run(date(2025,1,1)); assert r.run(date(2025,1,1))['reused']; assert r.run(date(2025,1,1),retry=True)['run_key']!=a['run_key']

def test_concurrent_lock_rejected(tmp_path):
    a=RunLock(tmp_path/'x.lock','a'); a.acquire();
    with pytest.raises(RuntimeError): RunLock(tmp_path/'x.lock','b').acquire()
    a.release()

def test_weekly_report_aggregates_real_manifests(tmp_path):
    r=make_runner(tmp_path, fail_on=3, stale_on=5); ds=[date(2025,1,1)+timedelta(days=i) for i in range(7)]; [r.run(d) for d in ds]; report=r.weekly_report(ds)
    assert report['run_count']==7 and report['date_start']=='2025-01-01' and report['date_end']=='2025-01-07' and len(report['score_changes'])==7
    assert any(x is not None for x in report['score_changes']) and any(x is not None for x in report['confidence_changes']) and any(x is not None for x in report['allocation_changes'])
    assert report['provider_failure_count']>=1 and report['stale_count']>=1 and report['degraded_count']>=1 and report['frozen_count']>=1
    assert '2025-01-03' in report['affected_dates'] and '2025-01-05' in report['affected_dates']
    path, written=r.write_weekly_report(ds); assert path.exists() and 'provider_failure_count' in path.read_text(encoding='utf-8') and written['frozen_count']>=1

def test_schedule_schema_and_scripts():
    from pathlib import Path
    data=load_schedule(); assert data['timezone']=='Asia/Shanghai' and {j['command'] for j in data['jobs']}=={'shadow-run','weekly-shadow-report','weekly-review'}
    assert all(isinstance(j['enabled'], bool) and len(j['local_time']) == 5 for j in data['jobs'])
    assert any(j['frequency']=='weekly' and j.get('day') for j in data['jobs'])
    for path in ('scripts/run_live_daily.ps1','scripts/run_live_daily.sh','scripts/run_live_weekly.ps1','scripts/run_live_weekly.sh'):
        text=Path(path).read_text(encoding='utf-8'); assert ('shadow-run' in text) if 'daily' in path else ('weekly-shadow-report' in text)
