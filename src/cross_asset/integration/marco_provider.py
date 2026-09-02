"""Filesystem adapter for Marco Integration Contract v1.

This adapter is intentionally independent of the legacy macro engine.
Marco mode therefore cannot silently fall back to legacy macro computation.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import (
    ALLOCATABLE_ASSETS,
    REQUIRED_MACRO_DIMENSIONS,
    VIEWABLE_ASSETS,
    AssetView,
    AssetViewsContract,
    IntegrationManifest,
    IntegrationValidationReport,
    MarcoMacroState,
    contract_major,
    normalize_asset_id,
)

MANIFEST_FILE = "manifest.json"
MACRO_STATE_FILE = "macro_state.json"
ASSET_VIEWS_FILE = "asset_views.json"


class MarcoIntegrationError(RuntimeError):
    """Raised when a Marco bundle cannot be safely consumed."""

    def __init__(
        self,
        message: str,
        report: IntegrationValidationReport | None = None,
    ):
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class MarcoBundle:
    manifest: IntegrationManifest
    macro_state: MarcoMacroState
    asset_views: tuple[AssetView, ...]
    report: IntegrationValidationReport

    @property
    def allocatable_views(self) -> tuple[AssetView, ...]:
        return tuple(
            view for view in self.asset_views if view.asset_id in ALLOCATABLE_ASSETS
        )

    @property
    def viewable_views(self) -> tuple[AssetView, ...]:
        return tuple(
            view for view in self.asset_views if view.asset_id in VIEWABLE_ASSETS
        )


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarcoIntegrationError(
            f"missing required integration file: {path.name}"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MarcoIntegrationError(
            f"cannot read valid JSON from {path.name}: {exc}"
        ) from exc


def _failure(message: str) -> IntegrationValidationReport:
    return IntegrationValidationReport(status="FAIL", errors=[message])


def _normalize_views(
    contract: AssetViewsContract,
) -> tuple[tuple[AssetView, ...], list[str]]:
    normalized: list[AssetView] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw in contract.views:
        canonical = normalize_asset_id(raw.asset_id)
        if canonical not in VIEWABLE_ASSETS:
            raise MarcoIntegrationError(
                f"asset_id {raw.asset_id!r} normalizes to unsupported view {canonical!r}"
            )
        if canonical in seen:
            raise MarcoIntegrationError(
                f"duplicate asset view after alias normalization: {canonical}"
            )
        seen.add(canonical)
        if canonical != raw.asset_id:
            warnings.append(f"asset alias normalized: {raw.asset_id} -> {canonical}")
        normalized.append(raw.model_copy(update={"asset_id": canonical}))
    return tuple(normalized), warnings


class MarcoProvider:
    """Validate and consume one immutable Marco integration directory."""

    def __init__(self, integration_dir: str | Path):
        self.integration_dir = Path(integration_dir)

    def validate(
        self,
        *,
        at: datetime | None = None,
    ) -> IntegrationValidationReport:
        try:
            return self.load_bundle(at=at).report
        except MarcoIntegrationError as exc:
            return exc.report or _failure(str(exc))
        except ValidationError as exc:
            return _failure(f"schema mismatch: {exc}")

    def load_macro_state(
        self,
        *,
        at: datetime | None = None,
    ) -> MarcoMacroState:
        return self.load_bundle(at=at).macro_state

    def load_bundle(
        self,
        *,
        at: datetime | None = None,
    ) -> MarcoBundle:
        if not self.integration_dir.exists():
            raise MarcoIntegrationError(
                f"integration directory does not exist: {self.integration_dir}"
            )
        if not self.integration_dir.is_dir():
            raise MarcoIntegrationError(
                f"integration path is not a directory: {self.integration_dir}"
            )

        try:
            manifest = IntegrationManifest.model_validate(
                _read_json(self.integration_dir / MANIFEST_FILE)
            )
            macro = MarcoMacroState.model_validate(
                _read_json(self.integration_dir / MACRO_STATE_FILE)
            )
        except ValidationError as exc:
            report = _failure(f"schema mismatch: {exc}")
            raise MarcoIntegrationError(report.errors[0], report) from exc

        errors: list[str] = []
        warnings: list[str] = []

        if contract_major(manifest.contract_version) != contract_major(
            macro.contract_version
        ):
            errors.append(
                "manifest and macro_state contract_version major versions differ"
            )
        if _utc(manifest.as_of) != _utc(macro.as_of):
            errors.append("manifest.as_of must equal macro_state.as_of")
        if _utc(macro.data_cutoff) > _utc(manifest.as_of):
            errors.append("macro_state.data_cutoff is after manifest.as_of")

        validation_time = _utc(at) if at is not None else datetime.now(UTC)
        if _utc(manifest.as_of) > validation_time:
            errors.append(
                "Marco snapshot is from the future relative to validation time"
            )

        stale = manifest.status == "STALE" or macro.status == "STALE"
        if manifest.expires_at is None:
            warnings.append(
                "manifest.expires_at is missing; freshness is producer-status only"
            )
        elif _utc(manifest.expires_at) <= validation_time:
            stale = True
            warnings.append("Marco integration bundle has expired")

        if manifest.status == "FAILED" or macro.status == "FAILED":
            errors.append("Marco producer marked the integration payload FAILED")

        missing_dimensions = [
            name for name in REQUIRED_MACRO_DIMENSIONS if name not in macro.dimensions
        ]
        if missing_dimensions:
            warnings.append(
                "required downstream macro dimensions missing: "
                + ", ".join(missing_dimensions)
            )

        dimension_degraded = False
        for name, dimension in macro.dimensions.items():
            if dimension.status in {"FAILED", "DEGRADED"}:
                dimension_degraded = True
                warnings.append(
                    f"macro dimension {name} is {dimension.status}"
                )
            elif dimension.status == "STALE":
                stale = True
                warnings.append(f"macro dimension {name} is STALE")
            if dimension.score is None:
                dimension_degraded = True
                warnings.append(
                    f"macro dimension {name} score is missing; no zero imputation"
                )

        views_path = self.integration_dir / ASSET_VIEWS_FILE
        normalized_views: tuple[AssetView, ...] = ()
        views_degraded = False
        if views_path.exists():
            try:
                views_contract = AssetViewsContract.model_validate(
                    _read_json(views_path)
                )
            except ValidationError as exc:
                report = _failure(f"asset_views schema mismatch: {exc}")
                raise MarcoIntegrationError(report.errors[0], report) from exc

            if contract_major(views_contract.contract_version) != contract_major(
                manifest.contract_version
            ):
                errors.append(
                    "asset_views and manifest contract_version major versions differ"
                )
            if _utc(views_contract.as_of) != _utc(manifest.as_of):
                errors.append("asset_views.as_of must equal manifest.as_of")
            try:
                normalized_views, alias_warnings = _normalize_views(views_contract)
            except (MarcoIntegrationError, ValueError) as exc:
                errors.append(str(exc))
            else:
                warnings.extend(alias_warnings)
                for view in normalized_views:
                    if view.status in {"FAILED", "DEGRADED", "STALE"}:
                        views_degraded = True
                        warnings.append(
                            f"asset view {view.asset_id} is {view.status}"
                        )
                    if view.score is None:
                        views_degraded = True
                        warnings.append(
                            f"asset view {view.asset_id} score is missing; "
                            "no zero imputation"
                        )
                if views_contract.status == "FAILED":
                    errors.append("Marco producer marked asset_views FAILED")
                elif views_contract.status in {"DEGRADED", "STALE"}:
                    views_degraded = True
                    warnings.append(
                        f"asset_views producer status is {views_contract.status}"
                    )
        else:
            warnings.append(
                "asset_views.json is absent; only macro state will be consumed"
            )

        producer_degraded = (
            manifest.status == "DEGRADED"
            or macro.status == "DEGRADED"
            or dimension_degraded
            or views_degraded
        )
        status = (
            "FAIL"
            if errors
            else (
                "DEGRADED"
                if stale or producer_degraded or missing_dimensions
                else "PASS"
            )
        )
        report = IntegrationValidationReport(
            status=status,
            contract_version=manifest.contract_version,
            macro_status=macro.status,
            errors=errors,
            warnings=warnings,
            missing_dimensions=missing_dimensions,
            normalized_asset_ids=[
                view.asset_id for view in normalized_views
            ],
            legacy_fallback_used=False,
        )
        if errors:
            raise MarcoIntegrationError("; ".join(errors), report)
        return MarcoBundle(
            manifest=manifest,
            macro_state=macro,
            asset_views=normalized_views,
            report=report,
        )


def resolve_macro_source(
    macro_source: str,
    *,
    integration_dir: str | Path | None = None,
    legacy_factory: Callable[[], Any] | None = None,
    at: datetime | None = None,
) -> Any:
    """Resolve macro input without any cross-source fallback.

    Marco mode never invokes legacy_factory. A Marco validation failure is
    propagated to the caller. Legacy remains available but receives no new
    behavior in this integration layer.
    """

    source = macro_source.strip().lower()
    if source == "marco":
        if integration_dir is None:
            raise MarcoIntegrationError(
                "--integration-dir is required when --macro-source marco"
            )
        return MarcoProvider(integration_dir).load_macro_state(at=at)
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
    "ASSET_VIEWS_FILE",
    "MACRO_STATE_FILE",
    "MANIFEST_FILE",
    "MarcoBundle",
    "MarcoIntegrationError",
    "MarcoProvider",
    "resolve_macro_source",
]
