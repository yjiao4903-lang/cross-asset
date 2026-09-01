from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from cross_asset.live.locks import RunLock
from cross_asset.operations.backup import create_backup, verify_backup


def test_backup_verify_corruption_and_isolated_restore(tmp_path):
    root=tmp_path/'project'; (root/'data/db').mkdir(parents=True); (root/'config').mkdir(); (root/'data/manual_archive').mkdir(parents=True)
    duckdb.connect(str(root/'data/db/cross_asset.duckdb')).close(); (root/'config/a.yml').write_text('x: 1'); (root/'data/manual_archive/a.csv').write_text('a,b')
    backup=Path(create_backup(root,tmp_path/'backups')); assert verify_backup(backup)['valid']
    (backup/'config/a.yml').write_text('corrupt'); assert not verify_backup(backup)['valid']


class FakeClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def test_lock_rejects_second_and_recovers_at_exact_stale_boundary(tmp_path):
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    path = tmp_path / "run.lock"
    first = RunLock(path, "a", ttl_seconds=10, clock=clock)
    first.acquire()
    second = RunLock(path, "b", clock=clock)
    with pytest.raises(RuntimeError): second.acquire()
    with pytest.raises(RuntimeError, match="not stale"):
        second.recover()
    clock.advance(10)
    assert second.recover()
    assert not path.exists()
    first.release()


def test_lock_rejects_naive_injected_clock(tmp_path):
    lock = RunLock(
        tmp_path / "run.lock", clock=lambda: datetime.fromisoformat("2026-01-01T00:00:00")
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        lock.acquire()


def test_lock_exception_releases(tmp_path):
    path=tmp_path/'run.lock'
    with pytest.raises(ValueError), RunLock(path,'x'):
        raise ValueError('expected')
    assert not path.exists()
