"""CLI contracts. Implementations are lazy-imported to keep parallel modules optional."""
import atexit
import json

import typer

from .logging import configure_logging
from .settings import get_settings
from .weekly_cli import register_weekly_commands

app = typer.Typer(name="cross-asset", help="Local cross-asset allocation decision engine")
register_weekly_commands(app)
