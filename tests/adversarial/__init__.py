"""Adversarial E2E validation package (issue #137).

This directory carries an ``__init__.py`` on purpose. Without it, pytest imports
``tests/adversarial/conftest.py`` as the top-level module ``conftest``, which
shadows the repository-level ``tests/conftest.py`` and breaks existing tests that
do ``from conftest import approve_test_series`` whenever this directory is
collected first. The package marker gives the conftest a qualified module name.
"""
