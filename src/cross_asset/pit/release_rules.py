"""Reusable release/vintage selection rules."""

from datetime import UTC


def _utc(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def released_by(observations, decision_time):
    """Return only observations available to an investor at decision_time."""
    decision_time = _utc(decision_time)
    return [
        o
        for o in observations
        if _utc(o.get("available_at") if isinstance(o, dict) else o.available_at) <= decision_time
    ]


def latest_vintage(observations, decision_time):
    rows = released_by(observations, decision_time)
    if not rows:
        return None
    return max(
        rows,
        key=lambda o: (
            o.get("available_at") if isinstance(o, dict) else o.available_at,
            o.get("ingested_at") if isinstance(o, dict) else o.ingested_at,
        ),
    )
