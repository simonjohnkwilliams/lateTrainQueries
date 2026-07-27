"""Unit tests: canonical JSON is byte-stable and deterministic."""
from __future__ import annotations

from psa.core.canon import dumps, loads


def test_dumps_sorts_keys_and_is_compact():
    raw = dumps({"b": 2, "a": 1})
    assert raw == '{"a":1,"b":2}\n'


def test_dumps_roundtrip():
    obj = {"z": [1, 2], "m": {"x": True}}
    assert loads(dumps(obj)) == obj


def test_dumps_identical_twice():
    obj = {"findings": [], "meta": {"tool_version": "0.1.0"}}
    assert dumps(obj) == dumps(obj)
