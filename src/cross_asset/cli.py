"""CLI contracts. Implementations are lazy-imported to keep parallel modules optional."""

import typer

from .weekly_cli import register_weekly_commands

app = typer.Typer(name="cross-asset", help="Local cross-asset allocation decision engine")
register_weekly_commands(app)


def _load_main_commands() -> None:
    from . import cli_commands_a, cli_commands_b, cli_commands_c

    _ = (cli_commands_a, cli_commands_b, cli_commands_c)


_load_main_commands()


if __name__ == "__main__":
    app()
