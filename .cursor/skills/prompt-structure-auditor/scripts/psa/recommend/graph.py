"""Recommendation dependency graph + Recommended Plan (Release 2).

Internally this is a graph. The public UX is `psa plan` only — never say "graph".
"""
from __future__ import annotations

from dataclasses import dataclass

from psa.findings import Finding

_EFFORT_WEIGHT = {"Small": 1, "Medium": 2, "Large": 4}

_RULE_PLAN: dict[str, dict[str, str]] = {
    "DUP001": {
        "title": "Merge duplicated architectural guidance",
        "reason": "Duplicate instructions increase maintenance burden and drift risk.",
        "effort": "Small",
        "unblocks": "Later ordering and activation work uses a single source of truth.",
    },
    "ACT002": {
        "title": "Add activation frontmatter",
        "reason": "Without frontmatter, Cursor cannot decide when a rule should apply.",
        "effort": "Small",
        "unblocks": "Dormant-rule review becomes meaningful once activation metadata exists.",
    },
    "ACT001": {
        "title": "Review dormant rules",
        "reason": "Rules without activation intent stay silent and waste prompt context.",
        "effort": "Medium",
        "unblocks": "Rules apply only when intended.",
    },
    "STYLE001": {
        "title": "Separate worklog content from durable instructions",
        "reason": "Volatile worklog text poisons the stable instruction prefix.",
        "effort": "Medium",
        "unblocks": "Ordering fixes can target durable content only.",
    },
    "ORDER001": {
        "title": "Move volatile sections below stable guidance",
        "reason": "Early volatility breaks prompt-prefix reuse.",
        "effort": "Medium",
        "unblocks": "Stable instructions stay at the front of the file.",
    },
}

_ENABLES: tuple[tuple[str, str, str], ...] = (
    ("DUP001", "ORDER001", "Consolidate duplicates before reordering once"),
    ("STYLE001", "ORDER001", "Split worklog before reordering remaining durable content"),
    ("ACT002", "ACT001", "Add frontmatter before reviewing dormant activation"),
    ("ACT001", "ORDER001", "Fix activation before judging ordering of rule body"),
    ("ACT002", "ORDER001", "Add frontmatter before ordering analysis of the rule"),
)

_ENABLE_REASON: dict[tuple[str, str], str] = {
    (src, dst): reason for src, dst, reason in _ENABLES
}


@dataclass(frozen=True)
class Recommendation:
    finding_id: str
    rule_id: str
    action: str
    owner: str

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "action": self.action,
            "owner": self.owner,
        }


@dataclass(frozen=True)
class RecEdge:
    src: str
    dst: str
    relation: str
    reason: str
    src_rule: str = ""
    dst_rule: str = ""

    def to_dict(self) -> dict:
        return {
            "src": self.src,
            "dst": self.dst,
            "relation": self.relation,
            "reason": self.reason,
            "src_rule": self.src_rule,
            "dst_rule": self.dst_rule,
        }


@dataclass(frozen=True)
class PlanFindingRef:
    finding_id: str
    rule_id: str
    title: str

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "title": self.title,
        }


@dataclass(frozen=True)
class PlanRecommendation:
    """User-facing remediation step for the frozen psa plan contract."""

    id: str
    title: str
    priority: str
    reason: str
    addresses: tuple[str, ...]
    findings: tuple[PlanFindingRef, ...]
    estimated_effort: str
    depends_on: tuple[str, ...]
    expected_outcome: str
    why_now: str
    unblocks: str
    remaining_after: str
    rule_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "reason": self.reason,
            "addresses": list(self.addresses),
            "findings": [f.to_dict() for f in self.findings],
            "estimated_effort": self.estimated_effort,
            "depends_on": list(self.depends_on),
            "expected_outcome": self.expected_outcome,
            "why_now": self.why_now,
            "unblocks": self.unblocks,
            "remaining_after": self.remaining_after,
            "rule_ids": list(self.rule_ids),
        }


@dataclass(frozen=True)
class DependencyGraph:
    nodes: tuple[Recommendation, ...]
    edges: tuple[RecEdge, ...]
    roadmap: tuple[Recommendation, ...]
    cycles: tuple[tuple[str, ...], ...]
    plan: tuple[PlanRecommendation, ...] = ()

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "roadmap": [n.to_dict() for n in self.roadmap],
            "cycles": [list(c) for c in self.cycles],
            "plan": [p.to_dict() for p in self.plan],
        }


def build_recommendations(findings: tuple[Finding, ...]) -> DependencyGraph:
    user_findings = tuple(f for f in findings if f.ownership == "user")

    nodes: list[Recommendation] = [
        Recommendation(
            finding_id=f.id,
            rule_id=f.rule_id,
            action=f.recommendation,
            owner=f.ownership,
        )
        for f in user_findings
    ]
    by_rule: dict[str, list[Recommendation]] = {}
    for n in nodes:
        by_rule.setdefault(n.rule_id, []).append(n)

    edges: list[RecEdge] = []
    for src_rule, dst_rule, reason in _ENABLES:
        for src in by_rule.get(src_rule, []):
            for dst in by_rule.get(dst_rule, []):
                if src.finding_id == dst.finding_id:
                    continue
                edges.append(
                    RecEdge(
                        src=src.finding_id,
                        dst=dst.finding_id,
                        relation="enables",
                        reason=reason,
                        src_rule=src_rule,
                        dst_rule=dst_rule,
                    )
                )

    nodes_t = tuple(sorted(nodes, key=lambda n: (n.rule_id, n.finding_id)))
    edges_t = tuple(sorted(edges, key=lambda e: (e.src, e.dst, e.relation)))
    roadmap, cycles = _topo_findings(nodes_t, edges_t)
    plan = _build_plan(user_findings)
    return DependencyGraph(
        nodes=nodes_t,
        edges=edges_t,
        roadmap=roadmap,
        cycles=cycles,
        plan=plan,
    )


def _build_plan(findings: tuple[Finding, ...]) -> tuple[PlanRecommendation, ...]:
    if not findings:
        return ()

    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule_id, []).append(f)

    rule_order = sorted(by_rule.keys())
    rule_to_rec_id = {rule: f"REC{idx:03d}" for idx, rule in enumerate(rule_order, 1)}
    total = len(findings)

    drafts: list[PlanRecommendation] = []
    for rule in rule_order:
        group = sorted(by_rule[rule], key=lambda f: (f.title, f.id))
        meta = _RULE_PLAN.get(
            rule,
            {
                "title": f"Address {rule} findings",
                "reason": "Resolves related prompt-architecture findings.",
                "effort": "Medium",
                "unblocks": "Clears related findings for follow-on work.",
            },
        )
        n = len(group)
        refs = tuple(
            PlanFindingRef(finding_id=f.id, rule_id=f.rule_id, title=f.title.strip())
            for f in group
        )
        depends = [
            rule_to_rec_id[src]
            for src, dst, _ in _ENABLES
            if dst == rule and src in rule_to_rec_id
        ]
        depends_clean: list[str] = []
        seen_d: set[str] = set()
        for d in depends:
            if d not in seen_d:
                seen_d.add(d)
                depends_clean.append(d)

        drafts.append(
            PlanRecommendation(
                id=rule_to_rec_id[rule],
                title=meta["title"],
                priority=_priority_for(n, meta["effort"]),
                reason=meta["reason"],
                addresses=tuple(f.id for f in group),
                findings=refs,
                estimated_effort=meta["effort"],
                depends_on=tuple(depends_clean),
                expected_outcome=_outcome(n),
                why_now="",  # filled after ordering
                unblocks=meta.get("unblocks", ""),
                remaining_after="",  # filled after ordering
                rule_ids=(rule,),
            )
        )

    return _order_plan(tuple(drafts), total_findings=total)


def _outcome(n: int) -> str:
    return f"{n} finding resolved." if n == 1 else f"{n} findings resolved."


def _priority_for(finding_count: int, effort: str) -> str:
    weight = _EFFORT_WEIGHT.get(effort, 2)
    score = finding_count / weight
    if score >= 2.0:
        return "High"
    if score >= 1.0:
        return "Medium"
    return "Low"


def _value_score(rec: PlanRecommendation) -> float:
    weight = _EFFORT_WEIGHT.get(rec.estimated_effort, 2)
    return len(rec.addresses) / weight


def _order_plan(
    recs: tuple[PlanRecommendation, ...],
    *,
    total_findings: int,
) -> tuple[PlanRecommendation, ...]:
    by_id = {r.id: r for r in recs}
    ids = list(by_id.keys())
    succ: dict[str, list[str]] = {i: [] for i in ids}
    indeg: dict[str, int] = {i: 0 for i in ids}
    for r in recs:
        for dep in r.depends_on:
            if dep not in indeg:
                continue
            succ[dep].append(r.id)
            indeg[r.id] += 1

    def ready_key(i: str) -> tuple:
        r = by_id[i]
        return (-_value_score(r), r.id)

    ready = sorted([i for i, d in indeg.items() if d == 0], key=ready_key)
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
                ready.sort(key=ready_key)

    remaining = [i for i in ids if i not in order]
    if remaining:
        order.extend(sorted(remaining, key=ready_key))

    old_to_new = {old: f"REC{idx:03d}" for idx, old in enumerate(order, 1)}
    id_to_step = {old_to_new[old]: idx for idx, old in enumerate(order, 1)}
    id_to_title = {old_to_new[old]: by_id[old].title for old in order}
    id_to_rules = {old_to_new[old]: by_id[old].rule_ids for old in order}

    resolved = 0
    ordered: list[PlanRecommendation] = []
    for step_idx, old in enumerate(order, 1):
        r = by_id[old]
        new_id = old_to_new[old]
        new_depends = tuple(old_to_new[d] for d in r.depends_on if d in old_to_new)
        n = len(r.addresses)
        resolved += n
        remaining_n = total_findings - resolved
        why_now = _why_now(
            step_idx=step_idx,
            rec=r,
            depends_new=new_depends,
            id_to_step=id_to_step,
            id_to_title=id_to_title,
            id_to_rules=id_to_rules,
        )
        remaining_after = (
            f"{resolved} of {total_findings} findings addressed; "
            f"{remaining_n} remaining."
            if remaining_n
            else f"All {total_findings} findings addressed; repository should return to Healthy."
        )
        ordered.append(
            PlanRecommendation(
                id=new_id,
                title=r.title,
                priority=r.priority,
                reason=r.reason,
                addresses=r.addresses,
                findings=r.findings,
                estimated_effort=r.estimated_effort,
                depends_on=new_depends,
                expected_outcome=_outcome(n),
                why_now=why_now,
                unblocks=r.unblocks,
                remaining_after=remaining_after,
                rule_ids=r.rule_ids,
            )
        )
    return tuple(ordered)


def _why_now(
    *,
    step_idx: int,
    rec: PlanRecommendation,
    depends_new: tuple[str, ...],
    id_to_step: dict[str, int],
    id_to_title: dict[str, str],
    id_to_rules: dict[str, tuple[str, ...]],
) -> str:
    n = len(rec.addresses)
    parts: list[str] = []

    if depends_new:
        dep_bits = []
        for dep in depends_new:
            step_n = id_to_step.get(dep)
            title = id_to_title.get(dep, dep)
            label = f"Step {step_n} ({title})" if step_n else title
            dep_rules = id_to_rules.get(dep, ())
            dst_rule = rec.rule_ids[0] if rec.rule_ids else ""
            enable = ""
            for src_rule in dep_rules:
                enable = _ENABLE_REASON.get((src_rule, dst_rule), "")
                if enable:
                    break
            dep_bits.append(f"{label}: {enable}" if enable else label)
        parts.append("Depends on prior work - " + "; ".join(dep_bits) + ".")
        parts.append(
            f"Scheduled as Step {step_idx} once those blockers clear "
            f"({n} finding(s), {rec.estimated_effort} effort)."
        )
    else:
        parts.append(
            f"Scheduled as Step {step_idx} because it is unblocked and offers "
            f"strong value for effort: {n} finding(s) removed for "
            f"{rec.estimated_effort} effort."
        )

    if rec.unblocks:
        parts.append(f"Completing it unblocks: {rec.unblocks}")

    return " ".join(parts)


def _topo_findings(
    nodes: tuple[Recommendation, ...],
    edges: tuple[RecEdge, ...],
) -> tuple[tuple[Recommendation, ...], tuple[tuple[str, ...], ...]]:
    ids = [n.finding_id for n in nodes]
    by_id = {n.finding_id: n for n in nodes}
    succ: dict[str, list[str]] = {i: [] for i in ids}
    indeg: dict[str, int] = {i: 0 for i in ids}
    for e in edges:
        if e.src not in indeg or e.dst not in indeg:
            continue
        succ[e.src].append(e.dst)
        indeg[e.dst] += 1

    ready = sorted([i for i, d in indeg.items() if d == 0])
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(succ[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
                ready.sort()

    remaining = [i for i in ids if i not in order]
    cycles: list[tuple[str, ...]] = []
    if remaining:
        cycles.append(tuple(sorted(remaining)))
        order.extend(sorted(remaining))

    roadmap = tuple(by_id[i] for i in order if i in by_id)
    return roadmap, tuple(cycles)
