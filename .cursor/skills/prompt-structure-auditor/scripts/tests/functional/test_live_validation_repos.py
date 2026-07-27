"""Live IdeaProjects validation — part of the complete suite when paths exist.

VR1  ai-context-benchmark   — empty instruction surface / healthy
VR2  lateTrainQueries       — activation + duplication
VR3  financeTracker_SW      — healthy with CLAUDE.md

Format consistency across these repos is also locked in
tests/acceptance/test_releases_r1_r6.py (R1–R6 matrix).
"""
from __future__ import annotations

import pytest

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.report.audit_view import STATUS_HEALTHY, STATUS_NEEDS_ATTENTION, render_audit
from tests.conftest import LIVE_VR1, LIVE_VR2, LIVE_VR3, present_live_targets
from tests.contract import assert_frozen_audit_structure, normalized_audit_structure


@pytest.mark.skipif(
    len(present_live_targets()) < 3,
    reason="One or more live IdeaProjects repos missing",
)
def test_live_three_repos_identical_audit_structure():
    structures: dict[str, str] = {}
    for name, path, _ in present_live_targets():
        text = render_audit(
            analyze(LocalRepoFS(path), tool_version="0.1.0"),
            repo_name=path.name,
        )
        assert_frozen_audit_structure(text, name)
        structures[name] = normalized_audit_structure(text)
    assert len(set(structures.values())) == 1, (
        "Live repos do not share identical audit structure:\n"
        + "\n---\n".join(f"{k}\n{v}" for k, v in structures.items())
    )


@pytest.mark.skipif(not LIVE_VR1.is_dir(), reason="VR1 not present on this machine")
def test_live_vr1_healthy_empty_instructions():
    audit = analyze(LocalRepoFS(LIVE_VR1), tool_version="0.1.0")
    text = render_audit(audit, repo_name=LIVE_VR1.name)
    assert_frozen_audit_structure(text, "VR1")
    assert audit.findings == ()
    assert f"| Status | {STATUS_HEALTHY} |" in text
    assert "No prompt architecture issues detected" in text
    assert not any(
        ".cursor/skills/" in d or ".claude/skills/" in d or ".agents/" in d
        for d in audit.guidance
    )


@pytest.mark.skipif(not LIVE_VR2.is_dir(), reason="VR2 not present on this machine")
def test_live_vr2_activation_findings():
    audit = analyze(LocalRepoFS(LIVE_VR2), tool_version="0.1.0")
    text = render_audit(audit, repo_name=LIVE_VR2.name)
    assert_frozen_audit_structure(text, "VR2")
    act = [f for f in audit.findings if f.rule_id in {"ACT001", "ACT002"}]
    assert len(act) >= 1
    assert f"| Status | {STATUS_NEEDS_ATTENTION} |" in text
    assert not any(".claude/skills/" in d for d in audit.guidance)


@pytest.mark.skipif(not LIVE_VR3.is_dir(), reason="VR3 not present on this machine")
def test_live_vr3_finance_tracker_healthy():
    audit = analyze(LocalRepoFS(LIVE_VR3), tool_version="0.1.0")
    text = render_audit(audit, repo_name=LIVE_VR3.name)
    assert_frozen_audit_structure(text, "VR3")
    assert sum(1 for r in audit.inventory.rows if r.status == "present") >= 1
    assert audit.findings == ()
    assert f"| Status | {STATUS_HEALTHY} |" in text
    assert "No prompt architecture issues detected" in text
    assert not any(
        ".cursor/skills/" in d or ".claude/skills/" in d
        for d in audit.guidance
    )
