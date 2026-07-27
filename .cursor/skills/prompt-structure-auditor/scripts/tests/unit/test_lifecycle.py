"""Tests for baseline save/load and audit diff."""
from __future__ import annotations

from pathlib import Path

from tests.conftest import FIXTURES

from psa.core.canon import dumps
from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.lifecycle.baseline import load_baseline, save_baseline
from psa.lifecycle.diff import diff_audits


def test_baseline_roundtrip(tmp_path: Path):
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    path = tmp_path / "baseline.json"
    save_baseline(audit, path)
    loaded = load_baseline(path)
    assert dumps(loaded.to_dict()) == dumps(audit.to_dict())


def test_diff_introduced_and_resolved(tmp_path: Path):
    empty = analyze(LocalRepoFS(FIXTURES / "empty_repo"), tool_version="0.1.0")
    full = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    d = diff_audits(current=full, baseline=empty)
    assert d.introduced
    assert not d.resolved
    d2 = diff_audits(current=empty, baseline=full)
    assert d2.resolved
    assert not d2.introduced


def test_diff_unchanged_identical():
    a = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    d = diff_audits(current=a, baseline=a)
    assert set(d.unchanged) == {f.id for f in a.findings}
    assert not d.introduced
    assert not d.resolved
