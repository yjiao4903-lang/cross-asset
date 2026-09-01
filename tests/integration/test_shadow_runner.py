from datetime import UTC, date, datetime

from cross_asset.domain.models import Observation
from cross_asset.operations.shadow import ShadowRunner
from cross_asset.storage import init_db


def test_shadow_runner_uses_service_and_is_safe(tmp_path):
    def fetch(series):
        return [Observation(series_id=s, observation_date=date(2025, 1, 1), available_at=datetime(2025, 1, 2, tzinfo=UTC), value=1, source='simulated', source_series_id=s, frequency='daily', unit='fixture') for s in series]
    runner=ShadowRunner(init_db(':memory:'), tmp_path/'raw', tmp_path/'out', fetcher=fetch, lock_path=tmp_path/'lock')
    out=runner.run(date(2025, 1, 3)); assert out['run_mode']=='SHADOW' and out['no_trade'] and out['strategic_weights_unchanged']
    assert out['series_count']==8 and (tmp_path/'out/2025-01-03/run_manifest.json').exists()
    assert runner.run(date(2025, 1, 3))['reused']
