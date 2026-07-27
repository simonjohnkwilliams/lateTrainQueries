"""Release 1 frozen audit UX contract tests."""
from __future__ import annotations

import re

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS, MemoryRepoFS
from psa.report.audit_view import (
    FINDINGS_COLUMNS,
    FINDINGS_HEADING,
    REPORT_TITLE,
    STATUS_HEALTHY,
    STATUS_NEEDS_ATTENTION,
    SUMMARY_FIELDS,
    SUMMARY_HEADING,
    render_audit,
)
from tests.conftest import VR1, VR2, VR3


_FORBIDDEN_IN_AUDIT = (
    "Honesty note",
    "psa doctor",
    "Ignored (default",
    "data file",
    "Parser Failures",
    "Discovery Summary",
    "Prompt Surface Inventory",
    "Fix these first",
    "Implementation Roadmap",
    "Recommended Plan",
    "Estimated effort",
    "✅",
    "⚠",
)


def _section_order(text: str) -> list[str]:
    headings = []
    for line in text.splitlines():
        if line in (REPORT_TITLE, SUMMARY_HEADING, FINDINGS_HEADING):
            headings.append(line)
    return headings


def test_contract_identical_structure_healthy_and_issues():
    healthy = render_audit(analyze(LocalRepoFS(VR1), tool_version="0.1.0"), repo_name="vr1")
    issues = render_audit(analyze(LocalRepoFS(VR3), tool_version="0.1.0"), repo_name="vr3")
    assert _section_order(healthy) == [REPORT_TITLE, SUMMARY_HEADING, FINDINGS_HEADING]
    assert _section_order(issues) == [REPORT_TITLE, SUMMARY_HEADING, FINDINGS_HEADING]
    for text in (healthy, issues):
        for field in SUMMARY_FIELDS:
            assert f"| {field} |" in text
        assert "| " + " | ".join(FINDINGS_COLUMNS) + " |" in text
        for bad in _FORBIDDEN_IN_AUDIT:
            assert bad not in text


def test_contract_ascii_safe_output():
    for root, name in ((VR1, "vr1"), (VR3, "vr3")):
        text = render_audit(analyze(LocalRepoFS(root), tool_version="0.1.0"), repo_name=name)
        assert text.encode("ascii")


def test_contract_empty_findings_placeholder_row():
    text = render_audit(analyze(LocalRepoFS(VR1), tool_version="0.1.0"), repo_name="vr1")
    assert "| Findings | None |" in text
    assert f"| Status | {STATUS_HEALTHY} |" in text
    assert "No prompt architecture issues detected" in text
    assert "| - | - | No prompt architecture issues detected |" in text
    assert "Recommended Plan" not in text


def test_contract_issues_status_and_breakdown():
    text = render_audit(analyze(LocalRepoFS(VR2), tool_version="0.1.0"), repo_name="lateTrainQueries")
    assert f"| Status | {STATUS_NEEDS_ATTENTION} |" in text
    assert re.search(r"\| Findings \| \d+ \(", text)
    assert "| High | ACT" in text or "| High | ACT001 |" in text


def test_contract_guidance_counted():
    fs = MemoryRepoFS(
        {
            "AGENTS.md": "# A\nStable.\n",
            "docs/prompt-engineering.md": "# Prompts\n",
            "docs/coding-standards.md": "# Standards\n",
            ".serena/project.yml": "x: 1\n",
        }
    )
    audit = analyze(fs, tool_version="0.1.0")
    assert len(audit.guidance) >= 2
    text = render_audit(audit, repo_name="demo")
    assert "| Guidance |" in text
    assert "2 files" in text or re.search(r"\| Guidance \| \d+ files? \|", text)


def test_contract_guidance_excludes_general_markdown():
    from psa.discovery.documentation import is_guidance_path

    assert not is_guidance_path("docs/api.md", instruction_paths=set())
    assert not is_guidance_path("docs/CHANGELOG.md", instruction_paths=set())
    assert not is_guidance_path("README.md", instruction_paths=set())
    assert not is_guidance_path("docs/release-notes.md", instruction_paths=set())
    assert not is_guidance_path(
        ".cursor/skills/prompt-structure-auditor/SKILL.md", instruction_paths=set()
    )
    assert not is_guidance_path(
        ".claude/skills/bmad-agent-dev/SKILL.md", instruction_paths=set()
    )
    assert is_guidance_path("docs/prompt-engineering.md", instruction_paths=set())
    assert is_guidance_path("docs/AI-GUIDANCE.md", instruction_paths=set())
    assert is_guidance_path("docs/ai-workflow.md", instruction_paths=set())
    assert is_guidance_path("benchmark/prompt.md", instruction_paths=set())
    # Instruction assets never count as guidance
    assert not is_guidance_path("AGENTS.md", instruction_paths={"AGENTS.md"})

    fs = MemoryRepoFS(
        {
            "AGENTS.md": "# A\n",
            "docs/api.md": "# API\n",
            "CHANGELOG.md": "# Changes\n",
            "docs/prompt-engineering.md": "# Prompts\n",
            ".cursor/skills/foo/SKILL.md": "# skill\n",
        }
    )
    audit = analyze(fs, tool_version="0.1.0")
    assert audit.guidance == ("docs/prompt-engineering.md",)
    text = render_audit(audit, repo_name="demo")
    assert "| Guidance | 1 file |" in text


def test_contract_guidance_not_promoted_to_findings():
    fs = MemoryRepoFS(
        {
            "docs/AI-GUIDANCE.md": "## Current Focus: X\nVolatile worklog style.\n",
        }
    )
    audit = analyze(fs, tool_version="0.1.0")
    assert audit.guidance
    assert audit.findings == ()
    text = render_audit(audit, repo_name="docs-only")
    assert f"| Status | {STATUS_HEALTHY} |" in text
    assert "| Active Prompt Sources | 0 instruction files |" in text


def test_contract_guidance_only_repo_honest_counts():
    """docs/ai/ with no runtime instructions → Active Prompt Sources: 0, Guidance: N."""
    fs = MemoryRepoFS(
        {
            "docs/ai/standards.md": "# Standards\n",
            "docs/ai/playbook.md": "# Playbook\n",
            "docs/ai/design.md": "# Design\n",
            "docs/api.md": "# API (not guidance)\n",
        }
    )
    audit = analyze(fs, tool_version="0.1.0")
    assert audit.guidance == (
        "docs/ai/design.md",
        "docs/ai/playbook.md",
        "docs/ai/standards.md",
    )
    assert audit.findings == ()
    text = render_audit(audit, repo_name="guidance-only")
    assert "| Active Prompt Sources | 0 instruction files |" in text
    assert "| Guidance | 3 files |" in text
    assert f"| Status | {STATUS_HEALTHY} |" in text
