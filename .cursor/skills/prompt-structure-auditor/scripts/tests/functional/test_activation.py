"""Functional: ACT001 dormant Cursor rules on VR2."""
from __future__ import annotations

from tests.conftest import VR2

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS


def test_act001_dormant_rules_on_vr2():
    audit = analyze(LocalRepoFS(VR2), tool_version="0.1.0")
    act = [f for f in audit.findings if f.rule_id == "ACT001"]
    assert len(act) >= 2  # bmad-builder + implementation
    paths = " ".join(e.path for f in act for e in f.evidence)
    assert "bmad-builder.mdc" in paths or "implementation.mdc" in paths


def test_architecture_mdc_missing_frontmatter_flagged():
    audit = analyze(LocalRepoFS(VR2), tool_version="0.1.0")
    # architecture.mdc has no YAML frontmatter — ACT002 or ACT001 sibling
    related = [f for f in audit.findings if f.rule_id in {"ACT001", "ACT002"}]
    assert any("architecture.mdc" in e.path for f in related for e in f.evidence)
