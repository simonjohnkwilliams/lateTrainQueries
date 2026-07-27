"""Inventory and human/machine report rendering."""
from __future__ import annotations

from dataclasses import dataclass

from psa.core.ignore_globs import IgnoreMatch


@dataclass(frozen=True)
class InventoryRow:
    adapter: str
    label: str
    status: str  # present | absent | out_of_scope | config | ignored
    detail: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "adapter": self.adapter,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PromptSurfaceInventory:
    rows: tuple[InventoryRow, ...]

    def to_dict(self) -> dict:
        return {"rows": [r.to_dict() for r in self.rows]}


def build_inventory(
    sources,
    ignored: tuple[IgnoreMatch, ...] = (),
    *,
    known_absent_checks: bool = True,
) -> PromptSurfaceInventory:
    sources = tuple(sources)
    ignored = tuple(ignored)
    rows: list[InventoryRow] = []

    def has_instruction(adapter: str) -> bool:
        return any(s.adapter == adapter and s.subtype == "instruction" for s in sources)

    # Per-file instruction sources with attribution
    for s in sources:
        if s.subtype != "instruction":
            continue
        reason = s.inclusion_reason() if hasattr(s, "inclusion_reason") else s.reason
        rows.append(
            InventoryRow(
                adapter=s.adapter,
                label=s.path,
                status="present",
                detail="instruction",
                reason=reason or "Instruction source",
            )
        )

    # Absent family checks (only when no files for that adapter)
    checks = [
        ("claude", "Claude instructions"),
        ("agents", "AGENTS.md"),
        ("cursor_rules", "Cursor Rules"),
        ("copilot", "Copilot Instructions"),
    ]
    if known_absent_checks:
        for adapter, title in checks:
            if not has_instruction(adapter):
                rows.append(
                    InventoryRow(
                        adapter=adapter,
                        label=title,
                        status="absent",
                        detail="",
                        reason="Not found in repository",
                    )
                )

    for s in sources:
        if s.subtype == "config":
            reason = s.inclusion_reason() if hasattr(s, "inclusion_reason") else ""
            rows.append(
                InventoryRow(
                    adapter=s.adapter,
                    label=s.path,
                    status="config",
                    detail="config (not instruction)",
                    reason=reason or "Tool config",
                )
            )
        elif s.subtype == "data":
            reason = s.inclusion_reason() if hasattr(s, "inclusion_reason") else ""
            rows.append(
                InventoryRow(
                    adapter=s.adapter,
                    label=s.path,
                    status="out_of_scope",
                    detail="data (not audited)",
                    reason=reason or "Data (not instruction)",
                )
            )

    for m in ignored:
        rows.append(
            InventoryRow(
                adapter="ignore",
                label=m.display_root.rstrip("/"),
                status="ignored",
                detail=m.pattern,
                reason=m.reason,
            )
        )

    status_rank = {
        "present": 0,
        "config": 1,
        "ignored": 2,
        "absent": 3,
        "out_of_scope": 4,
    }
    rows.sort(key=lambda r: (status_rank.get(r.status, 9), r.adapter, r.label))
    return PromptSurfaceInventory(rows=tuple(rows))


def render_inventory(inv: PromptSurfaceInventory) -> str:
    lines = ["Prompt Surface Inventory", ""]
    groups = {
        "present": "Discovered (instruction)",
        "config": "Discovered (config, not instruction)",
        "ignored": "Ignored (default exclusion)",
        "absent": "Not found",
        "out_of_scope": "Out of scope (data)",
    }
    for status, title in groups.items():
        group = [r for r in inv.rows if r.status == status]
        if not group:
            continue
        lines.append(title)
        mark = {
            "present": "[x]",
            "config": "[c]",
            "ignored": "[!]",
            "absent": "[ ]",
            "out_of_scope": "[-]",
        }[status]
        for r in group:
            extra = f"  {r.detail}" if r.detail and status != "ignored" else ""
            if status == "ignored" and r.detail:
                extra = f"  ({r.detail})"
            lines.append(f"  {mark} {r.label}{extra}")
            if r.reason:
                lines.append(f"      Reason: {r.reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_human(audit) -> str:
    lines: list[str] = []
    lines.append("Prompt Structure Audit")
    lines.append("")
    lines.append(render_inventory(audit.inventory).rstrip())
    lines.append("")

    instruction_present = any(r.status == "present" for r in audit.inventory.rows)
    lines.append("Executive Summary")
    if not instruction_present:
        lines.append(
            "  No prompt instruction surface found "
            "(no CLAUDE.md / AGENTS.md / Cursor rules / Copilot instructions)."
        )
        lines.append("  Honest empty result: nothing to structurally audit.")
    else:
        by_pri: dict[str, int] = {}
        for f in audit.findings:
            by_pri[f.priority] = by_pri.get(f.priority, 0) + 1
        lines.append(f"  Findings: {len(audit.findings)}")
        for band in ("High value", "Medium value", "Low value", "Informational"):
            if band in by_pri:
                lines.append(f"  {band}: {by_pri[band]}")

    graph = getattr(audit, "dependency_graph", None)
    if graph and graph.roadmap:
        lines.append("")
        lines.append("Fix these first (roadmap)")
        seen_rules: list[str] = []
        headlines: list = []
        for n in graph.roadmap:
            if n.rule_id in seen_rules:
                continue
            seen_rules.append(n.rule_id)
            headlines.append(n)
            if len(headlines) >= 3:
                break
        for i, n in enumerate(headlines, 1):
            lines.append(f"  {i}. [{n.rule_id}] {n.action[:140]}")
        extra = []
        for rid in [n.rule_id for n in graph.roadmap]:
            if rid not in {h.rule_id for h in headlines} and rid not in extra:
                extra.append(rid)
        if extra:
            lines.append(
                f"  ... then {len(extra)} more rule(s) after the above "
                "(see Implementation Roadmap)."
            )
        if graph.edges:
            lines.append("  Dependencies")
            seen: set[tuple[str, str]] = set()
            for e in graph.edges:
                key = (e.src_rule, e.dst_rule)
                if key in seen or not e.src_rule:
                    continue
                seen.add(key)
                lines.append(
                    f"    - Do not apply [{e.dst_rule}] until [{e.src_rule}] "
                    f"({e.reason})."
                )
    lines.append("")

    lines.append("Findings")
    if not audit.findings:
        lines.append("  (none)")
    else:
        for f in audit.findings:
            lines.append(
                f"[{f.rule_id}] {f.priority} · {f.verification} · {f.observability} · owner: {f.ownership}"
            )
            lines.append(f.title)
            lines.append("Evidence")
            for e in f.evidence:
                span = f"{e.span[0]}-{e.span[1]}" if e.span else "?"
                lines.append(f"  {e.path}:{span}  {e.excerpt!r}")
            lines.append("Why it matters")
            lines.append(f"  {f.explanation}")
            lines.append("Recommendation")
            lines.append(f"  {f.recommendation}")
            lines.append("")
    lines.append("Honesty note")
    lines.append(
        "  This audit reports structure observable from repository contents. "
        "It does not measure or predict cache hit rate, cost, or latency."
    )
    if graph and graph.roadmap:
        lines.append("")
        lines.append("Implementation Roadmap")
        for i, n in enumerate(graph.roadmap, 1):
            lines.append(f"  {i}. [{n.rule_id}] {n.action[:120]}")
        if graph.cycles:
            lines.append("  Cycles detected (not silently broken):")
            for c in graph.cycles:
                lines.append(f"    {', '.join(c)}")
    return "\n".join(lines).rstrip() + "\n"
