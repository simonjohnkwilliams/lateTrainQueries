"""Frozen Release 1 audit report — public UX contract.

Exactly three headings, always, in this order:

1. Prompt Structure Auditor  (report title)
2. Summary                   (fixed fields table)
3. Findings                  (table; placeholder row when empty)

Release 2+ planning is a separate capability (`psa plan`) and must not appear here.
Future releases may append sections *after* Findings only on their own commands —
not by changing this audit contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psa.core.pipeline import Audit
    from psa.findings import Finding

# Public contract — do not rename or reorder without a major version bump.
REPORT_TITLE = "Prompt Structure Auditor"
SUMMARY_HEADING = "Summary"
FINDINGS_HEADING = "Findings"
SUMMARY_FIELDS = (
    "Repository",
    "Active Prompt Sources",
    "Guidance",
    "Configuration",
    "Status",
    "Findings",
)
FINDINGS_COLUMNS = ("Severity", "Rule", "Issue")

STATUS_HEALTHY = "Healthy"
STATUS_NEEDS_ATTENTION = "Needs Attention"
EMPTY_FINDINGS_ISSUE = "No prompt architecture issues detected"

_PRIORITY_ORDER = ("High value", "Medium value", "Low value", "Informational")
_SEVERITY = {
    "High value": "High",
    "Medium value": "Medium",
    "Low value": "Low",
    "Informational": "Informational",
}


def render_audit(audit: Audit, *, repo_name: str | None = None) -> str:
    """Stable day-to-day audit text (CLI default). ASCII-safe for Windows consoles."""
    n_instr = sum(1 for r in audit.inventory.rows if r.status == "present")
    n_config = sum(1 for r in audit.inventory.rows if r.status == "config")
    n_guidance = len(audit.guidance)

    name = _ascii_cell(repo_name or "repository")
    status = STATUS_HEALTHY if not audit.findings else STATUS_NEEDS_ATTENTION
    findings_cell = _findings_summary_cell(audit.findings)

    instr_label = (
        f"{n_instr} instruction file"
        if n_instr == 1
        else f"{n_instr} instruction files"
    )
    guidance_label = (
        f"{n_guidance} file" if n_guidance == 1 else f"{n_guidance} files"
    )
    config_label = f"{n_config} file" if n_config == 1 else f"{n_config} files"

    summary_values = {
        "Repository": name,
        "Active Prompt Sources": instr_label,
        "Guidance": guidance_label,
        "Configuration": config_label,
        "Status": status,
        "Findings": findings_cell,
    }

    lines: list[str] = [
        REPORT_TITLE,
        "",
        SUMMARY_HEADING,
        "",
        "| Field | Result |",
        "| --- | --- |",
    ]
    for field in SUMMARY_FIELDS:
        lines.append(f"| {field} | {summary_values[field]} |")

    lines.extend(
        [
            "",
            FINDINGS_HEADING,
            "",
            _findings_header_row(),
            "| --- | --- | --- |",
        ]
    )
    if not audit.findings:
        lines.append(f"| - | - | {EMPTY_FINDINGS_ISSUE} |")
    else:
        for f in _sorted_findings(audit.findings):
            sev = _SEVERITY.get(f.priority, f.priority)
            issue = _short_issue(f)
            lines.append(f"| {sev} | {f.rule_id} | {issue} |")

    lines.append("")
    return "\n".join(lines)


def repo_display_name(root: str | Path) -> str:
    return Path(root).resolve().name


def _ascii_cell(value: str) -> str:
    """Keep report printable on default Windows consoles without UTF-8 setup."""
    return value.encode("ascii", errors="replace").decode("ascii")


def _findings_summary_cell(findings: tuple) -> str:
    if not findings:
        return "None"
    counts: dict[str, int] = {}
    for f in findings:
        label = _SEVERITY.get(f.priority, f.priority)
        counts[label] = counts.get(label, 0) + 1
    parts = []
    for band in ("High", "Medium", "Low", "Informational"):
        if band in counts:
            parts.append(f"{counts[band]} {band}")
    detail = ", ".join(parts) if parts else ""
    total = len(findings)
    return f"{total} ({detail})" if detail else str(total)


def _sorted_findings(findings: tuple) -> list:
    rank = {p: i for i, p in enumerate(_PRIORITY_ORDER)}

    def key(f: Finding) -> tuple:
        return (rank.get(f.priority, 99), f.rule_id, f.title, f.id)

    return sorted(findings, key=key)


def _findings_header_row() -> str:
    return "| " + " | ".join(FINDINGS_COLUMNS) + " |"


def _short_issue(f: Finding) -> str:
    title = f.title.strip().replace("|", "/")
    if len(title) > 72:
        title = title[:69].rstrip() + "..."
    return _ascii_cell(title)
