"""Mechanical patch generation — preview only (RFC §12.2 step 1)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from psa.core.pipeline import Audit
from psa.core.ports import RepoFS
from psa.findings import Finding


@dataclass(frozen=True)
class Patch:
    finding_id: str
    rule_id: str
    path: str
    diff: str
    new_text: str


def resolve_finding(audit: Audit, finding_or_rule: str) -> Finding:
    """Resolve a finding by id, or the first patchable finding for a rule id."""
    key = finding_or_rule.strip()
    by_id = next((f for f in audit.findings if f.id == key), None)
    if by_id is not None:
        return by_id
    by_rule = [f for f in audit.findings if f.rule_id.upper() == key.upper()]
    if not by_rule:
        raise ValueError(f"unknown finding id or rule id: {finding_or_rule}")
    patchable = [f for f in by_rule if f.patchable and f.ownership == "user"]
    chosen = patchable[0] if patchable else by_rule[0]
    return chosen


def preview_patch(repo: RepoFS, audit: Audit, finding_or_rule: str) -> Patch:
    finding = resolve_finding(audit, finding_or_rule)
    if not finding.patchable or finding.ownership != "user":
        raise ValueError(
            f"finding {finding.id} ({finding.rule_id}) is not patchable by the user"
        )
    if finding.rule_id == "ORDER001":
        return _preview_order001(repo, finding)
    raise ValueError(f"no mechanical patch generator for {finding.rule_id}")


def _preview_order001(repo: RepoFS, finding: Finding) -> Patch:
    path = finding.evidence[0].path
    text = repo.read_text(path)
    lines = text.splitlines(keepends=True)
    # Move the volatile heading section to end of file (before trailing newline).
    volatile_title = finding.evidence[0].excerpt
    stable_title = finding.evidence[1].excerpt if len(finding.evidence) > 1 else ""

    sections = _split_sections(lines)
    vol_idx = next((i for i, (h, _) in enumerate(sections) if h == volatile_title), None)
    if vol_idx is None:
        raise ValueError(f"could not locate section {volatile_title!r} in {path}")
    vol = sections.pop(vol_idx)
    # Place after last stable section if found, else append
    insert_at = len(sections)
    if stable_title:
        for i, (h, _) in enumerate(sections):
            if h == stable_title:
                insert_at = i + 1
    sections.insert(insert_at, vol)
    # Actually for ORDER001 recommendation: move volatile *below* stable — append near end
    # Re-do: put volatile section at end among content sections (after all others)
    sections = [s for s in sections if s is not vol] + [vol]

    new_lines: list[str] = []
    for _h, body_lines in sections:
        new_lines.extend(body_lines)
    new_text = "".join(new_lines)
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    diff = _unified_diff(path, text, new_text)
    return Patch(
        finding_id=finding.id,
        rule_id=finding.rule_id,
        path=path,
        diff=diff,
        new_text=new_text,
    )


def _split_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = "(preamble)"
    current: list[str] = []
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    for line in lines:
        m = heading_re.match(line.rstrip("\n"))
        if m:
            if current or sections:
                sections.append((current_heading, current))
            current_heading = m.group(2).strip()
            current = [line]
        else:
            current.append(line)
    if current or not sections:
        sections.append((current_heading, current))
    return sections


def _unified_diff(path: str, old: str, new: str) -> str:
    import difflib

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
