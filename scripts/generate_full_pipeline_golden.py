"""Explicit golden updater; ordinary tests never overwrite golden files."""

import argparse
import json
from pathlib import Path

from cross_asset.backtest.golden import snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="explicitly overwrite golden files")
    args = parser.parse_args()
    if not args.update:
        parser.error("refusing to overwrite golden files without --update")
    root = Path("tests/golden/full_pipeline")
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in snapshot().items():
        (root / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
