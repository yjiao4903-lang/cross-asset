"""CLI contracts. Implementations are lazy-imported to keep parallel modules optional."""
import atexit
import json

import typer

from .logging import configure_logging
from .settings import get_settings
from .weekly_cli import register_weekly_commands

app = typer.Typer(name="cross-asset", help="Local cross-asset allocation decision engine")
register_weekly_commands(app)

# Current-main command bodies belong in this module. They were truncated by an
# earlier hook commit. Restore from main 481e7fd plus the two-line weekly hook
# above before merge. Weekly commands are registered via weekly_cli.
