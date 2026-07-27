"""Determinism / purity: core must not touch clock, network, or RNG."""
from __future__ import annotations

import datetime as datetime_mod  # noqa: F401 — reserved for future purity hooks
import random as random_mod
import socket as socket_mod
import time as time_mod

from tests.conftest import VR3

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS


def test_analyze_rejects_impure_calls(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("impure call during analyze")

    monkeypatch.setattr(time_mod, "time", boom)
    monkeypatch.setattr(time_mod, "sleep", boom)
    # datetime.datetime.now is not patchable on all Python builds; cover time/random/socket.
    monkeypatch.setattr(random_mod, "random", boom)
    monkeypatch.setattr(socket_mod, "socket", boom)

    audit = analyze(LocalRepoFS(VR3), tool_version="0.1.0")
    assert audit is not None


def test_double_run_identical_machine_json():
    from psa.core.canon import dumps

    fs = LocalRepoFS(VR3)
    a = dumps(analyze(fs, tool_version="0.1.0").to_dict())
    b = dumps(analyze(fs, tool_version="0.1.0").to_dict())
    assert a == b
