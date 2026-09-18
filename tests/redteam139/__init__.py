"""Adversarial closure suite for #139 (LOCAL-DEV-A MULTIWEEK-MONITORING-CLOSURE-REDTEAM-V1).

This directory is an importable package on purpose: an un-packaged
``tests/<dir>/conftest.py`` shadows the top-level ``tests/conftest.py`` under
pytest's prepend import mode (recorded as ADV-P2-10 in #138).
"""

from __future__ import annotations
