"""Story 1.1 AC1: the scaffolded ``trainline`` package imports as stubs.

Every module in the hexagonal layout exists and imports without error, so later
stories have a home. Runs offline with no network or credentials (NFR2).
"""
import importlib

import pytest

MODULES = [
    "trainline",
    "trainline.engine",
    "trainline.engine.models",
    "trainline.engine.delay",
    "trainline.engine.optimiser",
    "trainline.adapters",
    "trainline.adapters.hsp_client",
    "trainline.adapters.storage",
    "trainline.adapters.config",
    "trainline.cli",
]


@pytest.mark.offline
@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name):
    assert importlib.import_module(module_name) is not None
