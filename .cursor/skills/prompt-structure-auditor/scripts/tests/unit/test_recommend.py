"""Unit/behaviour tests for recommendation graph + frozen psa plan (Release 2)."""
from __future__ import annotations

import pytest

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.recommend.graph import build_recommendations
from psa.report.audit_view import render_audit
from psa.report.plan_view import DETAILS_HEADING, PLAN_HEADING, render_plan
from tests.conftest import FIXTURES, LIVE_VR2
from tests.contract_plan import assert_frozen_plan_structure


def test_recommendations_only_for_user_owned_findings():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    graph = build_recommendations(audit.findings)
    assert graph.nodes
    assert all(n.owner == "user" for n in graph.nodes)


def test_plan_groups_findings_by_rule():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    plan = audit.dependency_graph.plan
    assert plan
    rules_in_plan = [r for p in plan for r in p.rule_ids]
    assert len(rules_in_plan) == len(set(rules_in_plan))
    for step in plan:
        assert step.id.startswith("REC")
        assert step.estimated_effort in {"Small", "Medium", "Large"}
        assert step.addresses
        assert step.findings
        assert step.why_now
        assert step.remaining_after
        assert step.expected_outcome


def test_plan_orders_by_value_with_dependencies():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    plan = audit.dependency_graph.plan
    rule_seq = [p.rule_ids[0] for p in plan]
    if "DUP001" in rule_seq and "ORDER001" in rule_seq:
        assert rule_seq.index("DUP001") < rule_seq.index("ORDER001")
    if "STYLE001" in rule_seq and "ORDER001" in rule_seq:
        assert rule_seq.index("STYLE001") < rule_seq.index("ORDER001")


def test_plan_command_output_separate_from_audit():
    audit = analyze(LocalRepoFS(FIXTURES / "vr3_demo"), tool_version="0.1.0")
    audit_text = render_audit(audit, repo_name="vr3_demo")
    plan_text = render_plan(audit, repo_name="vr3_demo")
    assert PLAN_HEADING not in audit_text
    assert DETAILS_HEADING not in audit_text
    assert_frozen_plan_structure(plan_text)
    assert "Why now" in plan_text
    assert "Expected end state" in plan_text
    assert "Unblocks" not in plan_text
    assert "graph" not in plan_text.lower()


def test_healthy_plan_empty_placeholder():
    audit = analyze(LocalRepoFS(FIXTURES / "vr1_empty"), tool_version="0.1.0")
    text = render_plan(audit, repo_name="vr1")
    assert_frozen_plan_structure(text)
    assert "No action needed" in text
    assert "No remediation steps required" in text
    assert "Why this order" not in text


@pytest.mark.skipif(not LIVE_VR2.is_dir(), reason="VR2 live missing")
def test_live_vr2_plan_intelligent_sequence():
    audit = analyze(LocalRepoFS(LIVE_VR2), tool_version="0.1.0")
    text = render_plan(audit, repo_name=LIVE_VR2.name)
    assert_frozen_plan_structure(text)
    plan = audit.dependency_graph.plan
    assert len(plan) >= 2
    assert plan[0].rule_ids[0] == "DUP001"
    assert "Why now" in text
    assert "Expected end state" in text
    assert "Unblocks" not in text
    assert PLAN_HEADING not in render_audit(audit, repo_name=LIVE_VR2.name)


def test_cycles_reported():
    from psa.recommend.graph import RecEdge, Recommendation, _topo_findings

    nodes = (
        Recommendation("a", "ORDER001", "do a", "user"),
        Recommendation("b", "DUP001", "do b", "user"),
    )
    edges = (
        RecEdge("a", "b", "enables", "a before b", "ORDER001", "DUP001"),
        RecEdge("b", "a", "enables", "b before a", "DUP001", "ORDER001"),
    )
    order, cycles = _topo_findings(nodes, edges)
    assert cycles
    assert len(cycles[0]) >= 2
