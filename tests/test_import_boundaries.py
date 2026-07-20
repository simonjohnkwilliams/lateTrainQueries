"""Story 1.1 AC2: enforce the hexagonal import boundaries (AD-1, AD-2, AD-9).

- Nothing under ``trainline/engine`` imports an I/O module.
- Nothing under ``trainline/engine`` imports a ``trainline.adapters`` module.
- No adapter imports another adapter.

Uses static AST analysis (not runtime import) so it works on stub modules and
never triggers an I/O import side effect.
"""
import ast
import os

import pytest

PKG_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "trainline"))
ENGINE_DIR = os.path.join(PKG_ROOT, "engine")
ADAPTERS_DIR = os.path.join(PKG_ROOT, "adapters")

# I/O / side-effecting modules the pure domain core must never import (AD-1).
FORBIDDEN_IO = {
    "os", "io", "sys", "json", "csv", "pathlib", "configparser",
    "sqlite3", "socket", "smtplib", "urllib", "http", "requests",
    "pickle", "shutil", "subprocess", "logging", "tempfile", "shelve",
}

ADAPTER_NAMES = {
    "hsp_client", "storage", "config", "notification", "ticket_gate", "ticket_intake",
    "swr_mapping", "claim_submission", "ollama_vision", "schedule_window",
    "ticket_quality", "weekly_marker", "ticket_drop",
}


def _iter_py_files(directory):
    for root, _dirs, files in os.walk(directory):
        if "__pycache__" in root:
            continue
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def _imported_module_paths(path):
    """Return the set of module paths a file imports.

    Relative imports (``from . import x`` / ``from ..adapters import y``) are
    rendered with leading dots so sibling-adapter references are detectable.
    Also records bare imported names (``from . import config`` → ``config``)
    so AD-2 peer-adapter imports cannot hide behind alias-only forms.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            names.add(prefix + (node.module or ""))
            for alias in node.names:
                # ``from . import config`` / ``from trainline.adapters import config``
                names.add(alias.name)
                if node.module:
                    names.add(prefix + node.module + "." + alias.name)
    return names


def _top_level(module_path):
    return module_path.lstrip(".").split(".")[0]


@pytest.mark.offline
def test_engine_imports_no_io():
    offenders = {}
    for path in _iter_py_files(ENGINE_DIR):
        bad = {m for m in _imported_module_paths(path)
               if _top_level(m) in FORBIDDEN_IO}
        if bad:
            offenders[os.path.relpath(path, PKG_ROOT)] = sorted(bad)
    assert not offenders, f"engine modules import I/O: {offenders}"


@pytest.mark.offline
def test_engine_imports_no_adapter():
    offenders = {}
    for path in _iter_py_files(ENGINE_DIR):
        bad = {m for m in _imported_module_paths(path) if "adapters" in m}
        if bad:
            offenders[os.path.relpath(path, PKG_ROOT)] = sorted(bad)
    assert not offenders, f"engine modules import adapters: {offenders}"


@pytest.mark.offline
def test_adapters_import_engine_models_only():
    # AD-2: adapters may import engine.models only — not engine.delay/optimiser.
    offenders = {}
    for path in _iter_py_files(ADAPTERS_DIR):
        bad = {
            m for m in _imported_module_paths(path)
            if "engine" in m and "engine.models" not in m and not m.endswith("engine")
        }
        if bad:
            offenders[os.path.relpath(path, PKG_ROOT)] = sorted(bad)
    assert not offenders, f"adapter imports engine internals beyond models: {offenders}"


@pytest.mark.offline
def test_no_adapter_imports_another_adapter():
    offenders = {}
    for path in _iter_py_files(ADAPTERS_DIR):
        this_adapter = os.path.splitext(os.path.basename(path))[0]
        others = ADAPTER_NAMES - {this_adapter}
        bad = set()
        for module_path in _imported_module_paths(path):
            for other in others:
                if (f"adapters.{other}" in module_path
                        or module_path == other
                        or module_path.endswith(f".{other}")):
                    bad.add(module_path)
        if bad:
            offenders[os.path.relpath(path, PKG_ROOT)] = sorted(bad)
    assert not offenders, f"adapter imports another adapter: {offenders}"
