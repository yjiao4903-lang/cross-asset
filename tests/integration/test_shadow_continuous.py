from datetime import UTC, date, datetime, timedelta

from cross_asset.domain.models import Observation
from cross_asset.operations.shadow import ShadowRunner
from cross_asset.storage import init_db


def test_shadow_seven_dates_failure_stale_and_weekly(tmp_path):
    base=datetime(2025,1,1,tzinfo=UTC); calls={'n':0}
    def fetch(series):
        calls['n']+=1
        if calls['n']==3: raise RuntimeError('provider down')
        quality='stale' if calls['n']==4 else 'ok'
        return [Observation(series_id=s,observation_date=base.date(),available_at=base,value=100+calls['n'],source='simulated',source_series_id=s,frequency='daily',unit='fixture',quality=quality) for s in series]
    r=ShadowRunner(init_db(':memory:'),tmp_path/'raw',tmp_path/'out',fetcher=fetch,lock_path=tmp_path/'lock'); dates=[date(2025,1,1)+timedelta(days=i) for i in range(7)]
    outputs=[r.run(d) for d in dates]
    assert len(outputs)==7 and outputs[2]['status']=='DEGRADED' and outputs[3]['allocation_status']=='FROZEN'
    weekly=r.weekly_report(dates); assert weekly['run_count']==7 and weekly['degraded_count']==1 and weekly['frozen_count']==1
    assert weekly['date_start']=='2025-01-01' and weekly['date_end']=='2025-01-07'
