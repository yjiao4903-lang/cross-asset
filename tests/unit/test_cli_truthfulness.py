import pytest
from typer.testing import CliRunner

from cross_asset.cli import app

RUNNER = CliRunner()
RESERVED = (
    "build-features",
    "score-market",
    "score-macro",
    "score-style",
    "score-assets",
    "allocate",
    "replay",
)


@pytest.mark.parametrize("command", RESERVED)
def test_reserved_pipeline_commands_exit_nonzero_and_identify_status(command: str):
    result = RUNNER.invoke(app, [command])

    assert result.exit_code != 0
    assert "NOT_IMPLEMENTED" in result.stdout
    assert "RESERVED" in result.stdout
    assert "no pipeline work was executed" in result.stdout


@pytest.mark.parametrize("command", RESERVED)
def test_reserved_pipeline_help_is_truthful(command: str):
    result = RUNNER.invoke(app, [command, "--help"])

    assert result.exit_code == 0, result.stdout
    assert "NOT_IMPLEMENTED" in result.stdout
    assert "RESERVED" in result.stdout


def test_fixture_backtest_help_is_explicitly_offline_only():
    result = RUNNER.invoke(app, ["backtest", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "FIXTURE_ONLY" in result.stdout
    assert "offline research" in result.stdout
    assert "Research validity is not claimed" in result.stdout
