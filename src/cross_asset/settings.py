"""Application settings and repository paths.

This module deliberately contains no provider or storage imports so it is safe
to import from every pipeline stage.
"""

import os
from functools import lru_cache
from pathlib import Path


def load_fred_api_key(env_path: str | Path | None = None) -> str | None:
    """Load only FRED_API_KEY, with process environment taking precedence."""
    current = os.environ.get("FRED_API_KEY")
    if current:
        return current
    path = Path(env_path) if env_path else Path(__file__).resolve().parents[2] / ".env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("FRED_API_KEY="):
                value = line.partition("=")[2].strip().strip("\"").strip("'")
                return value or None
    except (OSError, UnicodeError):
        return None
    return None

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # Keep domain/config inspection usable before optional env deps are installed.
    from pydantic import BaseModel

    BaseSettings = BaseModel  # type: ignore[misc,assignment]

    def SettingsConfigDict(**_: object) -> dict[str, object]:
        return {}


class Settings(BaseSettings):
    """Environment-backed settings with stable local defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fred_api_key: str | None = None
    tushare_token: str | None = None
    wind_enabled: bool = False
    ifind_enabled: bool = False
    cross_asset_data_dir: Path = Path("data")
    cross_asset_config_dir: Path = Path("config")
    cross_asset_log_level: str = "INFO"

    @property
    def raw_dir(self) -> Path:
        return self.cross_asset_data_dir / "raw"

    @property
    def database_path(self) -> Path:
        return self.cross_asset_data_dir / "db" / "cross_asset.duckdb"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
