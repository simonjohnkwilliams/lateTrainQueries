"""Unit tests for quiet audit and doctor presentation."""
from __future__ import annotations

from psa.core.config import DEFAULT_CONFIG
from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS, MemoryRepoFS
from psa.discovery import discover
from psa.report.audit_view import (
    FINDINGS_HEADING,
    REPORT_TITLE,
    STATUS_HEALTHY,
    STATUS_NEEDS_ATTENTION,
    SUMMARY_HEADING,
    render_audit,
)
from psa.report.doctor import render_doctor
from tests.conftest import VR1, VR3


def test_render_audit_healthy_empty_surface():
    audit = analyze(LocalRepoFS(VR1), tool_version="0.1.0")
    text = render_audit(audit, repo_name="vr1_empty")
    assert text.startswith(REPORT_TITLE)
    assert SUMMARY_HEADING in text
    assert FINDINGS_HEADING in text
    assert "vr1_empty" in text
    assert STATUS_HEALTHY in text
    assert "Honesty note" not in text
    assert "psa doctor" not in text
    assert "✅" not in text
    assert "⚠" not in text


def test_render_audit_findings_table():
    audit = analyze(LocalRepoFS(VR3), tool_version="0.1.0")
    text = render_audit(audit, repo_name="vr3_demo")
    assert STATUS_NEEDS_ATTENTION in text
    assert "| High | ORDER001 |" in text
    assert "| Severity | Rule | Issue |" in text


def test_render_doctor_verbose():
    fs = MemoryRepoFS(
        {
            "AGENTS.md": "# A\n",
            "tests/fixtures/AGENTS.md": "# ignore me\n",
            "docs/prompt-notes.md": "# notes\n",
        }
    )
    result = discover(fs, DEFAULT_CONFIG)
    text = render_doctor(result, DEFAULT_CONFIG)
    assert "Doctor" in text
    assert "Instruction Sources" in text
    assert "Guidance Surface" in text
    assert "Pattern matched" in text
    assert "--no-default-ignores" in text
