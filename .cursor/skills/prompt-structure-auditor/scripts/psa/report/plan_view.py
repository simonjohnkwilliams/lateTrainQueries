"""Frozen Release 2 plan report — public UX contract for `psa plan`.

Fixed order (every repo, every run):

1. Prompt Structure Plan
2. Summary
3. Recommended Plan          (overview table)
4. Recommendation Details    (compact per-step notes)
5. Expected end state

Future releases may append *after* Expected end state only.
Never merge into `psa audit`. Read-only — no preview/apply language.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psa.core.pipeline import Audit
    from psa.recommend.graph import PlanRecommendation

REPORT_TITLE = "Prompt Structure Plan"
SUMMARY_HEADING = "Summary"
PLAN_HEADING = "Recommended Plan"
DETAILS_HEADING = "Recommendation Details"
END_STATE_HEADING = "Expected end state"

SUMMARY_FIELDS = (
    "Repository",
    "Findings considered",
    "Recommendations",
    "Status",
)

# Why now is the scan column — strategy without reading every detail.
PLAN_COLUMNS = ("Step", "Recommendation", "Effort", "Resolves", "Why now")

STATUS_NO_ACTION = "No action needed"
STATUS_PLAN_READY = "Plan ready"
EMPTY_PLAN_ISSUE = "No remediation steps required"
STEP_SEPARATOR = "----------"


def render_plan(audit: Audit, *, repo_name: str | None = None) -> str:
    """Frozen day-to-day plan text. ASCII-safe for Windows consoles."""
    name = _ascii(repo_name or "repository")
    plan = getattr(audit.dependency_graph, "plan", ()) or ()
    n_findings = len(audit.findings)
    n_recs = len(plan)
    status = STATUS_NO_ACTION if n_recs == 0 else STATUS_PLAN_READY

    summary_values = {
        "Repository": name,
        "Findings considered": str(n_findings),
        "Recommendations": str(n_recs),
        "Status": status,
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
            PLAN_HEADING,
            "",
            "| " + " | ".join(PLAN_COLUMNS) + " |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    id_to_step = {step.id: i for i, step in enumerate(plan, 1)} if plan else {}

    if not plan:
        lines.append(f"| - | {EMPTY_PLAN_ISSUE} | - | - | - |")
    else:
        for i, step in enumerate(plan, 1):
            resolves = _resolves_label(len(step.addresses))
            why = _why_now_cell(step, id_to_step)
            title = _ascii(step.title).replace("|", "/")
            if len(title) > 48:
                title = title[:45].rstrip() + "..."
            lines.append(
                f"| {i} | {title} | {step.estimated_effort} | {resolves} | {why} |"
            )

    lines.extend(["", DETAILS_HEADING, ""])
    if not plan:
        lines.append(EMPTY_PLAN_ISSUE)
    else:
        for i, step in enumerate(plan, 1):
            lines.extend(_render_detail(i, step, id_to_step))
            if i < len(plan):
                lines.extend(["", STEP_SEPARATOR, ""])

    lines.extend(["", END_STATE_HEADING, "", _end_state(n_findings, n_recs), ""])
    return "\n".join(lines)


def _resolves_label(n: int) -> str:
    return f"{n} finding" if n == 1 else f"{n} findings"


def _why_now_cell(step: PlanRecommendation, id_to_step: dict[str, int]) -> str:
    """One-line strategy cue for the overview table."""
    if step.depends_on:
        deps = []
        for dep in step.depends_on:
            n = id_to_step.get(dep)
            deps.append(f"Step {n}" if n else dep)
        return _ascii(f"After {', '.join(deps)}")
    n = len(step.addresses)
    return _ascii(f"Best open value ({n} @ {step.estimated_effort})")


def _depends_label(step: PlanRecommendation, id_to_step: dict[str, int]) -> str:
    if not step.depends_on:
        return "None"
    parts = []
    for dep in step.depends_on:
        n = id_to_step.get(dep)
        parts.append(f"Step {n}" if n else dep)
    return ", ".join(parts)


def _render_detail(
    index: int,
    step: PlanRecommendation,
    id_to_step: dict[str, int],
) -> list[str]:
    """Compact detail: one Why block, resolves list, effort, progress — no Unblocks."""
    why = _compact_why(step, id_to_step)
    lines = [
        f"Step {index}",
        "",
        _ascii(step.title),
        "",
        "Why",
        "",
        _ascii(why),
        "",
        "Resolves",
        "",
    ]
    if step.findings:
        for f in step.findings:
            title = _ascii(f.title).replace("|", "/")
            if len(title) > 64:
                title = title[:61].rstrip() + "..."
            lines.append(f"- {f.rule_id}: {title}")
    else:
        lines.append(f"- {_resolves_label(len(step.addresses))}")

    lines.extend(
        [
            "",
            f"Effort: {step.estimated_effort}",
            f"Depends on: {_depends_label(step, id_to_step)}",
            f"After this step: {_ascii(step.remaining_after or step.expected_outcome)}",
        ]
    )
    return lines


def _compact_why(step: PlanRecommendation, id_to_step: dict[str, int]) -> str:
    """Single scannable paragraph — merge order rationale + substance, drop Unblocks."""
    n = len(step.addresses)
    bits: list[str] = []
    if step.depends_on:
        bits.append(f"Do after {_depends_label(step, id_to_step)}.")
    else:
        bits.append(
            f"Do first among open work: removes {n} for {step.estimated_effort} effort."
            if id_to_step.get(step.id, 1) == 1
            else f"Next open work: removes {n} for {step.estimated_effort} effort."
        )
    # One substance line (not a second "why" section)
    if step.reason:
        bits.append(_ascii(step.reason))
    return " ".join(bits)


def _end_state(n_findings: int, n_recs: int) -> str:
    if n_recs == 0:
        return "Already Healthy; no remediation required."
    return (
        f"Completing all {n_recs} steps should clear all {n_findings} findings "
        f"and return Status to Healthy."
    )


def _ascii(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii")
