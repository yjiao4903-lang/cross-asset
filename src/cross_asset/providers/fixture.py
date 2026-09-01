"""Deterministic offline provider used for contract and integration tests."""

from datetime import UTC, datetime

from .base import BaseProvider, Observation, ProviderCapability, ProviderError


class FixtureProvider(BaseProvider):
    name = "fixture"

    def probe(self):
        return ProviderCapability(
            provider=self.name,
            login="not_required",
            price="fixture",
            index="fixture",
            bond="fixture",
            macro="fixture",
            history="fixture",
            notes="Deterministic local data; not evidence of live vendor access.",
        )

    def fetch(self, request):
        values = self.config.get("values", {})
        if not values:
            return self._failure(
                ProviderError("empty_fixture", "Fixture has no values", provider=self.name)
            )
        # Fixed timestamp makes repeated fixture ingestion genuinely idempotent.
        now = self.config.get("available_at", datetime(2025, 1, 2, 16, tzinfo=UTC))
        if isinstance(now, str):
            now = datetime.fromisoformat(now)
        return [
            Observation(
                series_id=sid,
                observation_date=request.start or now.date(),
                available_at=now,
                value=float(value),
                source=self.name,
                source_series_id=sid,
                frequency="daily",
                unit="fixture",
            )
            for sid, value in values.items()
            if not request.series_ids or sid in request.series_ids
        ]
