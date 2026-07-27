"""Frozen public audit report contract helpers (Release 1).

Audit answers: What do I have, and is it healthy?
Plan is a separate capability (`psa plan`) and must not appear in audit text.
"""
from __future__ import annotations

from psa.report.audit_view import (
    FINDINGS_COLUMNS,
    FINDINGS_HEADING,
    REPORT_TITLE,
    SUMMARY_FIELDS,
    SUMMARY_HEADING,
)


def normalized_audit_structure(text: str) -> str:
    """Blank Summary values; keep headings/headers through Findings separator."""
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("| ") and line.count("|") == 3:
            field = line.split("|")[1].strip()
            if field in SUMMARY_FIELDS:
                lines.append(f"| {field} | <value> |")
                continue
        if lines and lines[-1] == "| --- | --- | --- |":
            break
        lines.append(line)
    return "\n".join(lines)


def assert_frozen_audit_structure(text: str, label: str = "audit") -> None:
    assert text.startswith(REPORT_TITLE), f"{label}: missing title"
    assert SUMMARY_HEADING in text and FINDINGS_HEADING in text, f"{label}: missing sections"
    for field in SUMMARY_FIELDS:
        assert f"| {field} |" in text, f"{label}: missing Summary field {field}"
    assert "| " + " | ".join(FINDINGS_COLUMNS) + " |" in text, f"{label}: Findings columns"
    i_title = text.index(REPORT_TITLE)
    i_summary = text.index(SUMMARY_HEADING)
    i_findings = text.index(FINDINGS_HEADING)
    assert i_title < i_summary < i_findings, f"{label}: section order"
    assert text.encode("ascii"), f"{label}: not ASCII-safe"
    assert "✅" not in text and "⚠" not in text, f"{label}: emoji in audit"
    for bad in (
        "Honesty note",
        "psa doctor",
        "Prompt Surface Inventory",
        "Fix these first",
        "Implementation Roadmap",
        "Parser Failures",
        "Recommended Plan",
        "Recommendation Graph",
        "dependency graph",
        "Estimated effort",
        "No remediation steps required.",
    ):
        assert bad not in text, f"{label}: leaked plan/artefact into audit: {bad!r}"
