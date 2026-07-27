"""Functional: ORDER001 on VR3; no false positive on VR1/VR2 references."""
from __future__ import annotations

from tests.conftest import VR1, VR2, VR3

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS


def test_order001_fires_on_vr3_current_focus_before_csv():
    audit = analyze(LocalRepoFS(VR3), tool_version="0.1.0")
    order = [f for f in audit.findings if f.rule_id == "ORDER001"]
    assert len(order) >= 1
    f = order[0]
    assert f.priority == "High value"
    assert f.verification == "confirmed"
    assert f.observability == "observable"
    assert f.ownership == "user"
    assert f.evidence
    assert "Current Focus" in f.title or "volatile" in f.title.lower() or "Current Focus" in f.explanation


def test_vr1_no_order001():
    audit = analyze(LocalRepoFS(VR1), tool_version="0.1.0")
    assert not any(f.rule_id == "ORDER001" for f in audit.findings)


def test_vr2_no_false_order001_from_bmad_references():
    audit = analyze(LocalRepoFS(VR2), tool_version="0.1.0")
    # Rules reference _bmad-output but do not embed volatile values first.
    assert not any(f.rule_id == "ORDER001" for f in audit.findings)
