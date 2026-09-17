from datetime import UTC, datetime
from types import SimpleNamespace

from cross_asset.decision_support.snapshot_cli import _previous_snapshot_for


class _Store:
    def __init__(self, candidate=None, *, missing: bool = False):
        self.candidate = candidate
        self.missing = missing

    def load_latest(self):
        if self.missing:
            raise FileNotFoundError("latest_snapshot_not_found")
        return self.candidate


def _snapshot(decision_time: datetime):
    return SimpleNamespace(metadata=SimpleNamespace(decision_time=decision_time))


def test_previous_snapshot_selection_is_strictly_economic_and_never_looks_ahead():
    current = datetime(2026, 9, 17, 1, tzinfo=UTC)
    earlier = _snapshot(datetime(2026, 9, 10, 1, tzinfo=UTC))
    equal = _snapshot(current)
    future = _snapshot(datetime(2026, 9, 18, 1, tzinfo=UTC))

    assert _previous_snapshot_for(_Store(earlier), current) is earlier
    assert _previous_snapshot_for(_Store(equal), current) is None
    assert _previous_snapshot_for(_Store(future), current) is None
    assert _previous_snapshot_for(_Store(missing=True), current) is None
