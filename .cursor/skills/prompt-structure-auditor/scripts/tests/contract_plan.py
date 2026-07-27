"""Frozen psa plan UX contract (Release 2+) — consistent across all repos/releases."""
from __future__ import annotations

from psa.report.plan_view import (
    DETAILS_HEADING,
    END_STATE_HEADING,
    PLAN_COLUMNS,
    PLAN_HEADING,
    REPORT_TITLE,
    SUMMARY_FIELDS,
    SUMMARY_HEADING,
)


def normalized_plan_structure(text: str) -> str:
    """Blank values; keep frozen headings through Expected end state."""
    lines: list[str] = []
    mode = "head"  # head | skip_plan | skip_details
    for line in text.splitlines():
        if line.startswith("| ") and line.count("|") == 3:
            field = line.split("|")[1].strip()
            if field in SUMMARY_FIELDS:
                lines.append(f"| {field} | <value> |")
                continue
        if line == "| --- | --- | --- | --- | --- |":
            lines.append(line)
            lines.append("| <plan rows> |")
            mode = "skip_plan"
            continue
        if mode == "skip_plan":
            if line == DETAILS_HEADING:
                lines.append(line)
                lines.append("<details>")
                mode = "skip_details"
            continue
        if mode == "skip_details":
            if line == END_STATE_HEADING:
                lines.append(line)
                lines.append("<end state>")
                break
            continue
        lines.append(line)
        if line == END_STATE_HEADING:
            lines.append("<end state>")
            break
    return "\n".join(lines)


def assert_frozen_plan_structure(text: str, label: str = "plan") -> None:
    assert text.startswith(REPORT_TITLE), f"{label}: missing title"
    assert SUMMARY_HEADING in text, f"{label}: missing Summary"
    assert PLAN_HEADING in text, f"{label}: missing Recommended Plan"
    assert DETAILS_HEADING in text, f"{label}: missing Recommendation Details"
    assert END_STATE_HEADING in text, f"{label}: missing Expected end state"
    for field in SUMMARY_FIELDS:
        assert f"| {field} |" in text, f"{label}: missing Summary field {field}"
    assert "| " + " | ".join(PLAN_COLUMNS) + " |" in text, f"{label}: plan columns"
    i_title = text.index(REPORT_TITLE)
    i_summary = text.index(SUMMARY_HEADING)
    i_plan = text.index(PLAN_HEADING)
    i_details = text.index(DETAILS_HEADING)
    i_end = text.index(END_STATE_HEADING)
    assert i_title < i_summary < i_plan < i_details < i_end, f"{label}: section order"
    assert text.encode("ascii"), f"{label}: not ASCII-safe"
    assert "Unblocks" not in text, f"{label}: Unblocks should not appear"
    for bad in ("graph", "Recommendation Graph", "Fix these first", "patch apply"):
        assert bad not in text, f"{label}: leaked {bad!r}"
