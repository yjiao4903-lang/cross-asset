from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from .base import BaseProvider, DataRequest, Observation, ProviderCapability, ProviderError


class ManualProvider(BaseProvider):
    name = "manual"

    def probe(self):
        return ProviderCapability(
            self.name,
            login="not_required",
            price="available",
            index="available",
            bond="available",
            macro="available",
            valuation="available",
            history="file-dependent",
            notes="Reads explicitly supplied CSV files; no network access.",
        )

    def fetch(self, request: DataRequest) -> list[Observation]:
        path = self.config.get("path")
        if not path:
            return self._failure(
                ProviderError(
                    "missing_input", "Manual provider requires path=...", provider=self.name
                )
            )
        try:
            file_path = Path(path)
            file_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
            with file_path.open(newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except (OSError, UnicodeError, csv.Error) as e:
            return self._failure(
                ProviderError(
                    "invalid_input",
                    "Could not read manual CSV",
                    provider=self.name,
                    details={"error": type(e).__name__},
                )
            )
        required = set(self.config.get("required_columns", ("observation_date", "value", "available_at")))
        if rows and not required.issubset(rows[0]):
            return self._failure(ProviderError("schema_error", "Manual template missing required columns", provider=self.name,
                details={"required_columns": sorted(required)}))
        mapping = self.config.get("series_mapping", {}) or {}
        out = []
        for row in rows:
            try:
                sid = row.get("series_id") or (mapping.get(row.get("source_series_id")) if mapping else None) or request.series_ids[0]
                d = datetime.fromisoformat(row["observation_date"]).date()
                # A manual observation's publication time is part of its PIT
                # contract.  Falling back to observation_date would silently
                # manufacture an information set and can introduce lookahead.
                if not row.get("available_at"):
                    raise ValueError("Manual CSV requires explicit available_at")
                avail = datetime.fromisoformat(row["available_at"])
                avail = (
                    avail.replace(tzinfo=UTC)
                    if avail.tzinfo is None
                    else avail.astimezone(UTC)
                )
                out.append(
                    Observation(
                        series_id=sid,
                        observation_date=d,
                        available_at=avail,
                        value=float(row["value"]) if row.get("value") not in (None, "") else None,
                        source=self.name,
                        source_series_id=row.get("source_series_id", sid),
                        ingested_at=datetime.now(UTC),
                        frequency="unknown",
                        unit="unknown",
                        metadata={"origin": "MANUAL", "template_id": self.config.get("template_id", "manual_csv_v1"), "file_hash": file_sha256, "file_sha256": file_sha256, "available_at": avail.isoformat()},
                    )
                )
            except (KeyError, IndexError, TypeError, ValueError):
                return self._failure(
                    ProviderError(
                        "schema_error",
                        "Manual CSV requires observation_date and numeric value",
                        provider=self.name,
                    )
                )
        return out
