"""Strict consumer for Marco Integration Contract v1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import (
    ALLOCATABLE_ASSETS,
    DATA_FILES,
    MANIFEST_FILE,
    FundamentalAsset,
    FundamentalAssetView,
    IntegrationManifest,
    IntegrationValidationReport,
    MacroSnapshot,
    SnapshotStatus,
    StructuralSnapshot,
    marco_to_cross_asset_id,
)

MACRO_SNAPSHOT_FILE = "macro_snapshot.json"
STRUCTURAL_SNAPSHOT_FILE = "structural_snapshot.json"
FUNDAMENTAL_ASSET_VIEW_FILE = "fundamental_asset_view.json"


class MarcoIntegrationError(RuntimeError):
    """Raised when Marco v1 cannot be consumed safely."""

    def __init__(
        self,
        message: str,
        report: IntegrationValidationReport | None = None,
    ) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class MarcoBundle:
    manifest: IntegrationManifest
    macro_snapshot: MacroSnapshot
    structural_snapshot: StructuralSnapshot
    fundamental_asset_view: FundamentalAssetView
    report: IntegrationValidationReport

    @property
    def cross_asset_fundamentals(self) -> dict[str, FundamentalAsset]:
        mapped: dict[str, FundamentalAsset] = {}
        for row in self.fundamental_asset_view.assets:
            cross_id = marco_to_cross_asset_id(row.asset_id)
            if cross_id is not None and cross_id in ALLOCATABLE_ASSETS:
                mapped[cross_id] = row
        return mapped

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "macro_snapshot": self.macro_snapshot.model_dump(mode="json"),
            "structural_snapshot": self.structural_snapshot.model_dump(mode="json"),
            "fx_views": [
                row.model_dump(mode="json")
                for row in self.fundamental_asset_view.fx_views
            ],
        }


def _failure(message: str) -> IntegrationValidationReport:
    return IntegrationValidationReport(
        status="FAIL",
        errors=[message],
        legacy_fallback_used=False,
    )


def _decision_date(value: date | datetime | str | None) -> date:
    if value is None:
        return datetime.now(UTC).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _read_json(path: Path) -> tuple[Any, bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise MarcoIntegrationError(
            f"required integration file unavailable: {path.name}"
        ) from exc
    try:
        return json.loads(payload.decode("utf-8")), payload
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarcoIntegrationError(f"invalid JSON in {path.name}: {exc}") from exc


def _signal_state(
    macro: MacroSnapshot,
    assets: FundamentalAssetView,
) -> tuple[str, list[str], list[str], list[str]]:
    unavailable_factors = [
        name
        for name, value in macro.factors.model_dump().items()
        if value["status"] != SnapshotStatus.READY
    ]
    unavailable_assets = [
        row.asset_id
        for row in assets.assets
        if row.status != SnapshotStatus.READY
    ]
    view_only_assets = [
        row.asset_id
        for row in assets.assets
        if marco_to_cross_asset_id(row.asset_id) is None
    ]
    signal_status = (
        "READY"
        if not unavailable_factors and not unavailable_assets
        else "PARTIAL"
    )
    return signal_status, unavailable_factors, unavailable_assets, view_only_assets


class MarcoProvider:
    """Read and validate the authoritative Marco v1 four-file bundle."""

    def __init__(self, integration_dir: str | Path) -> None:
        self.integration_dir = Path(integration_dir)

    def validate(
        self,
        *,
        at: date | datetime | str | None = None,
    ) -> IntegrationValidationReport:
        try:
            return self.load_bundle(at=at).report
        except MarcoIntegrationError as exc:
            return exc.report or _failure(str(exc))
        except ValidationError as exc:
            return _failure(f"schema mismatch: {exc}")

    def load_bundle(
        self,
        *,
        at: date | datetime | str | None = None,
    ) -> MarcoBundle:
        if not self.integration_dir.exists():
            raise MarcoIntegrationError(
                f"integration directory does not exist: {self.integration_dir}"
            )
        if not self.integration_dir.is_dir():
            raise MarcoIntegrationError(
                f"integration path is not a directory: {self.integration_dir}"
            )

        required = (*DATA_FILES, MANIFEST_FILE)
        missing = [
            name for name in required if not (self.integration_dir / name).is_file()
        ]
        if missing:
            report = _failure(
                "missing required Marco v1 files: " + ", ".join(sorted(missing))
            )
            raise MarcoIntegrationError(report.errors[0], report)

        raw: dict[str, bytes] = {}
        try:
            manifest_payload, raw[MANIFEST_FILE] = _read_json(
                self.integration_dir / MANIFEST_FILE
            )
            macro_payload, raw[MACRO_SNAPSHOT_FILE] = _read_json(
                self.integration_dir / MACRO_SNAPSHOT_FILE
            )
            structural_payload, raw[STRUCTURAL_SNAPSHOT_FILE] = _read_json(
                self.integration_dir / STRUCTURAL_SNAPSHOT_FILE
            )
            fundamental_payload, raw[FUNDAMENTAL_ASSET_VIEW_FILE] = _read_json(
                self.integration_dir / FUNDAMENTAL_ASSET_VIEW_FILE
            )
            manifest = IntegrationManifest.model_validate(manifest_payload)
            macro = MacroSnapshot.model_validate(macro_payload)
            structural = StructuralSnapshot.model_validate(structural_payload)
            fundamental = FundamentalAssetView.model_validate(fundamental_payload)
        except MarcoIntegrationError:
            raise
        except ValidationError as exc:
            report = _failure(f"schema mismatch: {exc}")
            raise MarcoIntegrationError(report.errors[0], report) from exc

        errors: list[str] = []
        warnings: list[str] = []

        for name in DATA_FILES:
            expected = manifest.files[name].sha256
            actual = hashlib.sha256(raw[name]).hexdigest()
            if actual != expected:
                errors.append(
                    f"SHA-256 mismatch for {name}: expected {expected}, got {actual}"
                )

        if macro.as_of != manifest.as_of:
            errors.append("macro_snapshot.as_of must equal manifest.as_of")
        if structural.as_of != manifest.as_of:
            errors.append("structural_snapshot.as_of must equal manifest.as_of")
        if fundamental.as_of != manifest.as_of:
            errors.append("fundamental_asset_view.as_of must equal manifest.as_of")
        if macro.data_cutoff != manifest.data_cutoff:
            errors.append("macro_snapshot.data_cutoff must equal manifest.data_cutoff")
        if fundamental.data_cutoff != manifest.data_cutoff:
            errors.append(
                "fundamental_asset_view.data_cutoff must equal manifest.data_cutoff"
            )
        if macro.model_version != manifest.marco_model_version:
            errors.append(
                "macro_snapshot.model_version must equal manifest.marco_model_version"
            )
        if fundamental.model_version != manifest.marco_model_version:
            errors.append(
                "fundamental_asset_view.model_version must equal manifest.marco_model_version"
            )
        if manifest.data_cutoff > manifest.as_of:
            errors.append("manifest.data_cutoff must be <= manifest.as_of")

        decision = _decision_date(at)
        if manifest.as_of > decision:
            errors.append(
                f"Marco snapshot as_of {manifest.as_of} is after decision_date {decision}"
            )
        if manifest.data_cutoff > decision:
            errors.append(
                f"Marco data_cutoff {manifest.data_cutoff} is after decision_date {decision}"
            )

        signal_status, unavailable_factors, unavailable_assets, view_only_assets = (
            _signal_state(macro, fundamental)
        )
        for name in unavailable_factors:
            status = getattr(macro.factors, name).status.value
            warnings.append(
                f"Marco factor {name} status={status}; missing is not zero-filled"
            )
        for row in fundamental.assets:
            if row.status != SnapshotStatus.READY:
                warnings.append(
                    f"Marco fundamental {row.asset_id} status={row.status.value}; "
                    "missing is not zero-filled"
                )
        if view_only_assets:
            warnings.append(
                "Marco assets outside the current Cross allocation universe remain "
                "diagnostic/view-only: " + ", ".join(view_only_assets)
            )

        report = IntegrationValidationReport(
            status="FAIL" if errors else "PASS",
            schema_version=manifest.schema_version,
            signal_status=signal_status,
            errors=errors,
            warnings=warnings,
            unavailable_factors=unavailable_factors,
            unavailable_assets=unavailable_assets,
            view_only_assets=view_only_assets,
            legacy_fallback_used=False,
        )
        if errors:
            raise MarcoIntegrationError("; ".join(errors), report)

        return MarcoBundle(
            manifest=manifest,
            macro_snapshot=macro,
            structural_snapshot=structural,
            fundamental_asset_view=fundamental,
            report=report,
        )


def resolve_macro_source(
    macro_source: str,
    *,
    integration_dir: str | Path | None = None,
    legacy_factory=None,
    at: date | datetime | str | None = None,
) -> Any:
    """Resolve the configured source without cross-source fallback."""

    source = macro_source.strip().lower()
    if source == "marco":
        if integration_dir is None:
            raise MarcoIntegrationError(
                "--integration-dir is required when --macro-source marco"
            )
        return MarcoProvider(integration_dir).load_bundle(at=at)
    if source == "legacy":
        if legacy_factory is None:
            raise MarcoIntegrationError(
                "legacy macro source requires legacy_factory"
            )
        return legacy_factory()
    raise MarcoIntegrationError(
        f"unsupported macro_source {macro_source!r}; expected legacy or marco"
    )


__all__ = [
    "FUNDAMENTAL_ASSET_VIEW_FILE",
    "MACRO_SNAPSHOT_FILE",
    "MANIFEST_FILE",
    "STRUCTURAL_SNAPSHOT_FILE",
    "MarcoBundle",
    "MarcoIntegrationError",
    "MarcoProvider",
    "resolve_macro_source",
]
