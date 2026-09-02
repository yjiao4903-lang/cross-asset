from typer.testing import CliRunner

from cross_asset.research.cli import app


def test_research_cli_help_is_available():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "Guarded real-data admission and OOS research workflows" in result.output
    for command in ("ingest", "readiness", "plan", "run-oos"):
        assert command in result.output


def test_research_ingest_help_is_available():
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0, result.output
    assert "Validate and optionally admit research observations" in result.output
