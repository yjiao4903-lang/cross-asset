import csv
import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from cross_asset.cli import app
from cross_asset.ingestion.acceptance import validate_data_file

FIELDS = {"series_id": "US_GOV_10Y", "provider": "manual", "source_series_id": "DGS10", "permission_scope": "research", "origin": "MANUAL", "observation_definition": "daily yield", "unit": "percent", "currency": "USD", "timezone": "UTC", "price_type": "yield", "adjustment_type": "none", "frequency": "daily", "history_start": "2020-01-01", "history_end": "2020-01-02", "observation_date_rule": "trading date", "available_at_rule": "explicit release timestamp", "vintage_rule": "retain vintage", "missing_policy": "unavailable", "semantic_equivalence": True, "template_version": "t1/v1", "reviewer": "reviewer", "approved_at": "2025-01-01T00:00:00+00:00", "reconciliation_notes": "checked", "available_at": "2020-01-02T12:00:00+00:00", "repeatability_evidence": [{"batch_id": "b1", "file_sha256": "a", "exported_at": "2025-01-01T00:00:00+00:00", "reviewer": "reviewer", "approved_at": "2025-01-01T01:00:00+00:00"}, {"batch_id": "b2", "file_sha256": "b", "exported_at": "2025-02-01T00:00:00+00:00", "reviewer": "reviewer", "approved_at": "2025-02-01T01:00:00+00:00"}, {"batch_id": "b3", "file_sha256": "c", "exported_at": "2025-03-01T00:00:00+00:00", "reviewer": "reviewer", "approved_at": "2025-03-01T01:00:00+00:00"}]}


def make_file(tmp_path, rows=None, manifest=None):
    path = tmp_path / "data.csv"
    rows = rows or [{"series_id": "US_GOV_10Y", "source_series_id": "DGS10", "observation_date": "2020-01-02", "available_at": "2020-01-02T12:00:00+00:00", "value": "1.2"}]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    if manifest is not None:
        payload = dict(FIELDS); payload.update(manifest); payload["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (tmp_path / "data.yml").write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_manual_file_passes_all_gates(tmp_path):
    result = validate_data_file(make_file(tmp_path, manifest={"origin": "MANUAL"}))
    assert result["status"] == "PASS" and result["gates"] == {"TECH": "PASS", "LEGAL": "PASS", "PIT": "PASS", "STABILITY": "PASS"}


def test_missing_manifest_hash_and_available_at_fail(tmp_path):
    path = make_file(tmp_path, rows=[{"series_id": "S", "value": "1"}], manifest=None)
    result = validate_data_file(path); assert result["status"] == "FAIL" and any(e["code"] == "manifest_required" for e in result["errors"])
    assert not Path(str(path).replace(".csv", ".yml")).exists()


def test_hash_duplicate_and_invalid_origin_fail(tmp_path):
    rows = [{"series_id": "S", "source_series_id": "S", "observation_date": "2020-01-01", "available_at": "2020-01-02T00:00:00+00:00", "value": "1"}] * 2
    path = make_file(tmp_path, rows=rows, manifest={"origin": "NOPE"})
    manifest = json.loads((tmp_path / "data.yml").read_text(encoding="utf-8")); manifest["file_sha256"] = "bad"; (tmp_path / "data.yml").write_text(json.dumps(manifest), encoding="utf-8")
    result = validate_data_file(path)
    codes = {e["code"] for e in result["errors"]}; assert result["status"] == "FAIL" and {"origin_invalid", "file_hash_mismatch", "duplicate_observation"} <= codes


def test_manual_requires_three_batches_and_fallback_metadata(tmp_path):
    result = validate_data_file(make_file(tmp_path, manifest={"batch_count": 1, "fallback": True}))
    codes = {w["code"] for w in result["warnings"]} | {e["code"] for e in result["errors"]}
    assert result["status"] == "FAIL" and "fallback_invalid" in codes


def test_manual_insufficient_batches_is_partial_and_cli_writes_deterministic_json(tmp_path):
    path = make_file(tmp_path, manifest={"batch_count": 1, "repeatability_evidence": []})
    result = validate_data_file(path); assert result["status"] == "PARTIAL" and result["gates"]["STABILITY"] == "UNKNOWN"
    output = tmp_path / "result.json"
    cli = CliRunner().invoke(app, ["validate-data-file", str(path), "--output", str(output)])
    assert cli.exit_code == 2 and json.loads(output.read_text(encoding="utf-8"))["status"] == "PARTIAL"


def test_canonical_manifest_and_preferred_discovery(tmp_path):
    path = make_file(tmp_path, manifest=None)
    payload = dict(FIELDS); payload["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "data.manifest.yml").write_text(json.dumps(payload), encoding="utf-8")
    result = validate_data_file(path)
    assert result["manifest"].endswith("data.manifest.yml")
    assert result["warnings"] == []


def test_legacy_fields_and_discovery_are_explicitly_warned(tmp_path):
    path = make_file(tmp_path, manifest=None)
    payload = dict(FIELDS); payload.update({"template_id": "legacy", "version": "1", "file_hash": hashlib.sha256(path.read_bytes()).hexdigest()})
    payload.pop("template_version", None); payload.pop("file_sha256", None)
    (tmp_path / "data.yml").write_text(json.dumps(payload), encoding="utf-8")
    result = validate_data_file(path)
    codes = {item["code"] for item in result["warnings"]}
    assert {"legacy_manifest_discovery", "legacy_manifest_field"} <= codes


def test_naive_available_at_and_empty_core_field_fail(tmp_path):
    path = make_file(tmp_path, manifest={"series_id": "", "approved_at": "2025-01-01T00:00:00+00:00"})
    rows = [{"series_id": "S", "source_series_id": "S", "observation_date": "2020-01-01", "available_at": "2020-01-02", "value": "1"}]
    path.unlink()
    path = make_file(tmp_path, rows=rows, manifest={})
    codes = {item["code"] for item in validate_data_file(path)["errors"]}
    assert {"core_field_invalid", "observation_invalid"} & codes


def test_fallback_semantics_and_history_order_fail(tmp_path):
    path = make_file(tmp_path, manifest={"semantic_equivalence": False, "fallback": True, "fallback_source": {"provider": "p", "source_series_id": "x"}, "history_start": "2021-01-01", "history_end": "2020-01-01"})
    codes = {item["code"] for item in validate_data_file(path)["errors"]}
    assert {"semantic_equivalence_invalid", "history_invalid"} <= codes


def test_pseudobatch_count_does_not_pass_manual_stability(tmp_path):
    result = validate_data_file(make_file(tmp_path, manifest={"batch_count": 99, "repeatability_evidence": "three"}))
    assert result["status"] == "PARTIAL" and result["gates"]["STABILITY"] == "UNKNOWN"


def test_three_batch_evidence_passes_manual_stability(tmp_path):
    result = validate_data_file(make_file(tmp_path, manifest={}))
    assert result["gates"]["STABILITY"] == "PASS"


def test_hash_and_duplicate_errors_are_deterministically_sorted(tmp_path):
    path = make_file(tmp_path, rows=[{"series_id": "S", "source_series_id": "S", "observation_date": "2020-01-01", "available_at": "2020-01-02T00:00:00+00:00", "value": "1"}] * 2, manifest={})
    payload = json.loads((tmp_path / "data.yml").read_text(encoding="utf-8")); payload["file_sha256"] = "bad"; (tmp_path / "data.yml").write_text(json.dumps(payload), encoding="utf-8")
    result = validate_data_file(path)
    assert result["errors"] == sorted(result["errors"], key=lambda item: (item["code"], item["message"]))


def test_cli_nested_output_for_missing_input_is_structured_fail(tmp_path):
    output = tmp_path / "nested" / "fail" / "result.json"
    cli = CliRunner().invoke(app, ["validate-data-file", str(tmp_path / "missing.csv"), "--output", str(output)])
    assert cli.exit_code == 1 and output.exists() and json.loads(output.read_text(encoding="utf-8"))["status"] == "FAIL"
    assert "Traceback" not in cli.stdout and isinstance(cli.exception, SystemExit)


def test_cli_nested_output_preserves_partial_and_pass_exit_codes(tmp_path):
    (tmp_path / "partial").mkdir()
    partial = make_file(tmp_path / "partial", manifest={"repeatability_evidence": []})
    partial_out = tmp_path / "nested" / "partial" / "result.json"
    partial_cli = CliRunner().invoke(app, ["validate-data-file", str(partial), "--output", str(partial_out)])
    assert partial_cli.exit_code == 2 and json.loads(partial_out.read_text(encoding="utf-8"))["status"] == "PARTIAL"
    (tmp_path / "pass").mkdir()
    passed = make_file(tmp_path / "pass", manifest={})
    pass_out = tmp_path / "nested" / "pass" / "result.json"
    pass_cli = CliRunner().invoke(app, ["validate-data-file", str(passed), "--output", str(pass_out)])
    assert pass_cli.exit_code == 0 and json.loads(pass_out.read_text(encoding="utf-8"))["status"] == "PASS"
