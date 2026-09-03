import json
import sys
import types

from typer.testing import CliRunner

from cross_asset.cli import app


def _install_canonicalizer_stub(monkeypatch, result):
    calls = []

    def canonicalize_wind_export(file, *, mapping, output, report, dry_run):
        calls.append(
            {
                "file": file,
                "mapping": mapping,
                "output": output,
                "report": report,
                "dry_run": dry_run,
            }
        )
        return result

    package = types.ModuleType("cross_asset.ingestion.wind_canonicalizer")
    package.canonicalize_wind_export = canonicalize_wind_export
    monkeypatch.setitem(sys.modules, "cross_asset.ingestion.wind_canonicalizer", package)
    return calls


def test_canonicalize_wind_export_help_is_available():
    result = CliRunner().invoke(app, ["canonicalize-wind-export", "--help"])

    assert result.exit_code == 0, result.output
    for option in ("--mapping", "--output", "--report", "--dry-run"):
        assert option in result.output
    assert "Wind raw" in result.output


def test_canonicalize_wind_export_dry_run_wires_options_without_ingestion(tmp_path, monkeypatch):
    input_file = tmp_path / "wind-export.xlsx"
    input_file.write_bytes(b"test fixture is not parsed by the CLI")
    output_file = tmp_path / "canonical.csv"
    report_file = tmp_path / "report.json"
    database = tmp_path / "should-not-exist.duckdb"
    calls = _install_canonicalizer_stub(
        monkeypatch,
        {"status": "READY", "dry_run": True, "canonical_rows": 0},
    )

    result = CliRunner().invoke(
        app,
        [
            "canonicalize-wind-export",
            str(input_file),
            "--mapping",
            "mapping.yml",
            "--output",
            str(output_file),
            "--report",
            str(report_file),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["dry_run"] is True
    assert calls == [
        {
            "file": str(input_file),
            "mapping": "mapping.yml",
            "output": str(output_file),
            "report": str(report_file),
            "dry_run": True,
        }
    ]
    assert not output_file.exists()
    assert not report_file.exists()
    assert not database.exists()


def test_canonicalize_wind_export_partial_uses_existing_partial_exit_convention(monkeypatch):
    _install_canonicalizer_stub(monkeypatch, {"status": "PARTIAL", "dry_run": True})

    result = CliRunner().invoke(app, ["canonicalize-wind-export", "input.xlsx", "--dry-run"])

    assert result.exit_code == 2, result.output


def test_production_importer_dry_run_contract_remains_cli_compatible(tmp_path):
    path = tmp_path / "canonical.csv"
    path.write_text(
        "series_id,observation_date,value,available_at,source,source_series_id,vintage_date,quality\n"
        "CN_EQ_LARGE,2026-01-01,100,2026-01-02T00:00:00+08:00,wind,000300.SH,,ok\n",
        encoding="utf-8",
    )
    database = tmp_path / "db.duckdb"
    raw_dir = tmp_path / "raw"

    result = CliRunner().invoke(
        app,
        [
            "ingest-production-csv",
            str(path),
            "--database",
            str(database),
            "--raw-dir",
            str(raw_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "VALID"
    assert payload["dry_run"] is True
    assert not database.exists()
    assert not raw_dir.exists()


def test_cli_real_conversion_output_is_accepted_by_production_importer(tmp_path):
    raw = tmp_path / "wind-export.csv"
    raw.write_text(
        "wind_code,instrument_name,date,value,unit,field_name,currency\n"
        "000300.SH,CSI 300,2026-09-02,101,points,close,CNY\n"
        "000300.SH,CSI 300,2026-09-01,100,points,close,CNY\n",
        encoding="utf-8",
    )
    mapping = tmp_path / "mapping.yml"
    mapping.write_text(
        "CN_EQ_LARGE:\n"
        "  source_series_id: 000300.SH\n"
        "  available_at_rule: CN_EQ_EOD_V1\n"
        "  available_at_basis: POLICY_DERIVED\n",
        encoding="utf-8",
    )
    output = tmp_path / "canonical.csv"
    report = tmp_path / "report.json"

    result = CliRunner().invoke(
        app,
        [
            "canonicalize-wind-export",
            str(raw),
            "--mapping",
            str(mapping),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "READY"
    assert output.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["series"][0]["field_name"] == "close"

    importer = CliRunner().invoke(
        app,
        [
            "ingest-production-csv",
            str(output),
            "--database",
            str(tmp_path / "db.duckdb"),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--dry-run",
        ],
    )
    assert importer.exit_code == 0, importer.output
    assert json.loads(importer.stdout)["status"] == "VALID"
    assert not (tmp_path / "db.duckdb").exists()
    assert not (tmp_path / "raw").exists()
