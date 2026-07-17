"""Shared pytest setup.

Puts the project root on sys.path so the ``trainline`` package imports cleanly
in the default (offline) test run. No network or credentials are required by
default (NFR2); live HSP and Ollama vision gates are opt-in.

Vision quality gate toggle (full golden set vs live Ollama):
  - Env:  ``TRAINLINE_VISION_GATE=1``
  - Flag: ``pytest --vision-gate``
  - Or:   ``pytest -m vision`` (vision tests only)

Live HSP remains: ``pytest -m live`` (needs HSP_CREDENTIALS_FILE).
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Truthy values for TRAINLINE_VISION_GATE
_VISION_GATE_ON = {"1", "true", "yes", "on"}


def _vision_gate_requested(config) -> bool:
    if config.getoption("--vision-gate"):
        return True
    raw = (os.environ.get("TRAINLINE_VISION_GATE") or "").strip().casefold()
    return raw in _VISION_GATE_ON


def pytest_addoption(parser):
    parser.addoption(
        "--vision-gate",
        action="store_true",
        default=False,
        help=(
            "Include @vision Ollama golden quality gate in this run "
            "(same as TRAINLINE_VISION_GATE=1). Requires local Ollama + "
            "trainline-ticket or qwen2.5vl:7b."
        ),
    )


def pytest_configure(config):
    """When the vision gate toggle is on, stop excluding @vision from defaults."""
    if not _vision_gate_requested(config):
        return
    markexpr = (getattr(config.option, "markexpr", None) or "").strip()
    # Default addopts is: not live and not vision — widen to not live only.
    if markexpr == "not live and not vision":
        config.option.markexpr = "not live"
    config._trainline_vision_gate = True  # type: ignore[attr-defined]


def pytest_report_header(config):
    gate = _vision_gate_requested(config)
    return [
        f"trainline vision gate: {'ON (--vision-gate / TRAINLINE_VISION_GATE)' if gate else 'off'}",
    ]
