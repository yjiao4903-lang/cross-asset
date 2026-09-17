from datetime import UTC, date, datetime

from cross_asset.decision_support.snapshot_cli import _previous_snapshot_for


class _Store:
    def __init__(self, candidate=None):
        self.candidate = candidate
        self.calls = []

    def prior_for(self, *, decision_time, current_week_id):
        self.calls.append((decision_time, current_week_id))
        return self.candidate


def test_previous_snapshot_selection_uses_canonical_history_and_economic_week():
    current = datetime(2026, 9, 17, 1, tzinfo=UTC)
    candidate = object()
    store = _Store(candidate)

    assert (
        _previous_snapshot_for(
            store,
            current,
            data_cutoff=date(2026, 9, 17),
        )
        is candidate
    )
    assert store.calls == [(current, "2026-09-14")]
