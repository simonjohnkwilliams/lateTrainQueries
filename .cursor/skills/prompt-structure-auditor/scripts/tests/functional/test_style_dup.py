"""Functional: STYLE001 worklog on VR3; DUP findings."""
from __future__ import annotations

from tests.conftest import VR2, VR3

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS


def test_style001_worklog_on_vr3():
    audit = analyze(LocalRepoFS(VR3), tool_version="0.1.0")
    style = [f for f in audit.findings if f.rule_id == "STYLE001"]
    assert len(style) >= 1
    assert style[0].ownership == "user"


def test_dup001_truelayer_on_vr3():
    audit = analyze(LocalRepoFS(VR3), tool_version="0.1.0")
    dups = [f for f in audit.findings if f.rule_id == "DUP001"]
    assert len(dups) >= 1


def test_dup_architecture_freeze_on_vr2():
    audit = analyze(LocalRepoFS(VR2), tool_version="0.1.0")
    dups = [f for f in audit.findings if f.rule_id == "DUP001"]
    # architecture freeze / do not redesign restated
    assert len(dups) >= 1
