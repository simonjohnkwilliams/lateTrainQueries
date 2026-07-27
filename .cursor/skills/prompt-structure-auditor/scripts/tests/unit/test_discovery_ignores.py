"""Unit tests for default discovery ignores and attribution."""
from __future__ import annotations

from psa.core.config import DEFAULT_CONFIG
from psa.core.ignore_globs import match_ignore
from psa.core.pipeline import analyze
from psa.core.ports import MemoryRepoFS
from psa.discovery import discover
from psa.report.doctor import render_doctor
from psa.report.inventory import render_inventory


SKILL_FIXTURE_AGENTS = (
    ".cursor/skills/prompt-structure-auditor/scripts/tests/fixtures/vr3_demo/AGENTS.md"
)


def test_match_tests_segment_at_any_depth():
    m = match_ignore(
        "scripts/tests/fixtures/vr3_demo/AGENTS.md",
        ("tests/**",),
    )
    assert m is not None
    assert m.display_root == "scripts/tests/"


def test_match_skill_install_tree():
    m = match_ignore(
        SKILL_FIXTURE_AGENTS,
        (".cursor/skills/**/scripts/tests/**", "fixtures/**"),
    )
    assert m is not None


def test_installed_skill_fixtures_not_audited():
    """FinanceTracker-style install must not audit skill test fixtures."""
    fs = MemoryRepoFS(
        {
            "README.md": "# app\n",
            "CLAUDE.md": "# Project\nStable guidance.\n",
            SKILL_FIXTURE_AGENTS: (
                "# Fixture\n## Current Focus: CSV Import\nVolatile.\n## Stable\nKeep.\n"
            ),
            ".cursor/skills/prompt-structure-auditor/scripts/tests/fixtures/vr3_demo/extra.md": "x",
        }
    )
    result = discover(fs)
    paths = {s.path for s in result.sources}
    assert "CLAUDE.md" in paths
    assert SKILL_FIXTURE_AGENTS not in paths
    assert result.ignored
    assert any("tests" in m.display_root for m in result.ignored)

    audit = analyze(fs, tool_version="0.1.0")
    assert audit.findings == ()
    text = render_inventory(audit.inventory)
    assert "CLAUDE.md" in text
    assert "Reason:" in text
    assert "Ignored" in text
    assert SKILL_FIXTURE_AGENTS.split("/")[-1] not in [
        r.label for r in audit.inventory.rows if r.status == "present"
    ]


def test_no_default_ignores_includes_fixtures():
    fs = MemoryRepoFS(
        {
            SKILL_FIXTURE_AGENTS: "# Fixture\n## Current Focus: X\nVol.\n## Stable\nOk.\n",
        }
    )
    result = discover(fs, DEFAULT_CONFIG.with_no_default_ignores())
    assert any(s.path == SKILL_FIXTURE_AGENTS for s in result.sources)
    assert result.ignored == ()


def test_root_agents_still_discovered():
    fs = MemoryRepoFS({"AGENTS.md": "# Real\nDo the thing.\n"})
    result = discover(fs)
    assert any(s.path == "AGENTS.md" for s in result.sources)
    assert result.ignored == ()


def test_render_doctor_summary():
    fs = MemoryRepoFS(
        {
            "AGENTS.md": "# A\n",
            "tests/fixtures/AGENTS.md": "# Should ignore\n",
        }
    )
    text = render_doctor(discover(fs), DEFAULT_CONFIG)
    assert "Doctor" in text
    assert "Instruction Sources" in text
    assert "Ignored" in text
    assert "--no-default-ignores" in text


def test_inventory_reason_attribution():
    fs = MemoryRepoFS(
        {
            "AGENTS.md": "# A\n",
            ".cursor/rules/java.mdc": "---\ndescription: x\nglobs: '*.java'\n---\nRule\n",
        }
    )
    audit = analyze(fs, tool_version="0.1.0")
    text = render_inventory(audit.inventory)
    assert "Reason: Agent instructions" in text
    assert "Reason: Cursor rule" in text
