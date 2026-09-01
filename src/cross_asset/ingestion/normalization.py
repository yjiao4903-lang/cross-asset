from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC

from cross_asset.providers.base import Observation


def normalize_observation(obs: Observation, *, source: str | None = None) -> Observation:
    """Normalize timezone and scalar value without filling missing values."""
    if obs.available_at.tzinfo is None:
        obs.available_at = obs.available_at.replace(tzinfo=UTC)
    else:
        obs.available_at = obs.available_at.astimezone(UTC)
    if obs.ingested_at.tzinfo is None:
        obs.ingested_at = obs.ingested_at.replace(tzinfo=UTC)
    else:
        obs.ingested_at = obs.ingested_at.astimezone(UTC)
    if obs.value is not None:
        obs.value = float(obs.value)
    if source:
        obs.source = source
    return obs


def normalize_observations(observations: Iterable[Observation], **kwargs) -> list[Observation]:
    return [normalize_observation(o, **kwargs) for o in observations]
