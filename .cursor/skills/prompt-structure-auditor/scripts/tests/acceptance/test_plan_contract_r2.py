"""Release 2 frozen psa plan UX contract tests."""
from __future__ import annotations

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.report.plan_view import (
    DETAILS_HEADING,
    END_STATE_HEADING,
    PLAN_COLUMNS,
    PLAN_HEADING,
    REPORT_TITLE,
    SUMMARY_FIELDS,
    SUMMARY_HEADING,
    render_plan,
)
from tests.conftest import LIVE_VR1, LIVE_VR2, LIVE_VR3, VR1, VR3, present_targets
from tests.contract_plan import assert_frozen_plan_structure, normalized_plan_structure


def _section_order(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line
        in (REPORT_TITLE, SUMMARY_HEADING, PLAN_HEADING, DETAILS_HEADING, END_STATE_HEADING)
    ]


def test_plan_contract_identical_structure_healthy_and_issues():
    healthy = render_plan(analyze(LocalRepoFS(VR1), tool_version="0.1.0"), repo_name="vr1")
    issues = render_plan(analyze(LocalRepoFS(VR3), tool_version="0.1.0"), repo_name="vr3")
    expected = [
        REPORT_TITLE,
        SUMMARY_HEADING,
        PLAN_HEADING,
        DETAILS_HEADING,
        END_STATE_HEADING,
    ]
    assert _section_order(healthy) == expected
    assert _section_order(issues) == expected
    for text in (healthy, issues):
        assert_frozen_plan_structure(text)
        assert "| " + " | ".join(PLAN_COLUMNS) + " |" in text


def test_plan_contract_empty_placeholder():
    text = render_plan(analyze(LocalRepoFS(VR1), tool_version="0.1.0"), repo_name="vr1")
    assert "| Status | No action needed |" in text
    assert "Already Healthy" in text
    assert "Unblocks" not in text


def test_plan_contract_scan_table_and_compact_details():
    text = render_plan(analyze(LocalRepoFS(VR3), tool_version="0.1.0"), repo_name="vr3")
    assert "| Status | Plan ready |" in text
    assert "Why now" in text  # column header
    assert "Best open value" in text or "After Step" in text
    assert "Why" in text
    assert "Resolves" in text
    assert "Effort:" in text
    assert "Depends on:" in text
    assert "After this step:" in text
    assert "Why this order" not in text
    assert "Why it matters" not in text
    assert "Unblocks" not in text
    assert "return Status to Healthy" in text


def test_plan_contract_all_present_targets_share_structure():
    structures: dict[str, str] = {}
    for name, path, _ in present_targets():
        text = render_plan(
            analyze(LocalRepoFS(path), tool_version="0.1.0"),
            repo_name=path.name,
        )
        assert_frozen_plan_structure(text, name)
        structures[name] = normalized_plan_structure(text)
    canonical = next(iter(structures.values()))
    for name, block in structures.items():
        assert block == canonical, f"{name} plan structure diverged:\n{block}"


def test_plan_live_repos_when_present():
    for label, path in (("VR1", LIVE_VR1), ("VR2", LIVE_VR2), ("VR3", LIVE_VR3)):
        if not path.is_dir():
            continue
        text = render_plan(
            analyze(LocalRepoFS(path), tool_version="0.1.0"),
            repo_name=path.name,
        )
        assert_frozen_plan_structure(text, label)


def test_plan_stays_out_of_preview_apply():
    text = render_plan(analyze(LocalRepoFS(VR3), tool_version="0.1.0"), repo_name="vr3")
    lower = text.lower()
    assert "preview" not in lower
    assert "apply" not in lower
    assert "patch" not in lower
