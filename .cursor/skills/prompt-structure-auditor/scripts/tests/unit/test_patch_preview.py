"""Tests for mechanical patch preview."""
from __future__ import annotations

from tests.conftest import FIXTURES

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.patch.generate import preview_patch


def test_preview_order001_produces_diff():
    fs = LocalRepoFS(FIXTURES / "vr3_demo")
    audit = analyze(fs, tool_version="0.1.0")
    order = next(f for f in audit.findings if f.rule_id == "ORDER001")
    patch = preview_patch(fs, audit, order.id)
    assert patch.diff
    assert "Current Focus" in patch.diff
    assert patch.finding_id == order.id


def test_preview_order001_by_rule_id():
    fs = LocalRepoFS(FIXTURES / "vr3_demo")
    audit = analyze(fs, tool_version="0.1.0")
    patch = preview_patch(fs, audit, "ORDER001")
    assert patch.rule_id == "ORDER001"
    assert "Current Focus" in patch.diff


def test_preview_refuses_non_patchable():
    fs = LocalRepoFS(FIXTURES / "vr3_demo")
    audit = analyze(fs, tool_version="0.1.0")
    style = next(f for f in audit.findings if f.rule_id == "STYLE001")
    try:
        preview_patch(fs, audit, style.id)
        raised = False
    except ValueError:
        raised = True
    assert raised
