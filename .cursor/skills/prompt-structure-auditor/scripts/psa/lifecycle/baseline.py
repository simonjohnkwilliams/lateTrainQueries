"""Baseline persistence."""
from __future__ import annotations

from pathlib import Path

from psa.core.canon import dumps, loads
from psa.core.pipeline import Audit, RunMeta
from psa.findings import Finding
from psa.model.types import Evidence
from psa.recommend.graph import (
    DependencyGraph,
    PlanFindingRef,
    PlanRecommendation,
    RecEdge,
    Recommendation,
)
from psa.report.inventory import InventoryRow, PromptSurfaceInventory


def save_baseline(audit: Audit, path: str | Path) -> None:
    Path(path).write_text(dumps(audit.to_dict()), encoding="utf-8")


def load_baseline(path: str | Path) -> Audit:
    data = loads(Path(path).read_text(encoding="utf-8"))
    return _audit_from_dict(data)


def _audit_from_dict(data: dict) -> Audit:
    from psa.core.pipeline import Audit as AuditCls

    findings = tuple(_finding_from_dict(f) for f in data.get("findings", []))
    inv_rows = tuple(
        InventoryRow(
            adapter=r["adapter"],
            label=r["label"],
            status=r["status"],
            detail=r.get("detail", ""),
            reason=r.get("reason", ""),
        )
        for r in data.get("inventory", {}).get("rows", [])
    )
    dep = data.get("dependency_graph") or {}
    plan = tuple(
        PlanRecommendation(
            id=p["id"],
            title=p["title"],
            priority=p["priority"],
            reason=p["reason"],
            addresses=tuple(p.get("addresses", [])),
            findings=tuple(
                PlanFindingRef(
                    finding_id=f["finding_id"],
                    rule_id=f["rule_id"],
                    title=f["title"],
                )
                for f in p.get("findings", [])
            ),
            estimated_effort=p["estimated_effort"],
            depends_on=tuple(p.get("depends_on", [])),
            expected_outcome=p["expected_outcome"],
            why_now=p.get("why_now", ""),
            unblocks=p.get("unblocks", ""),
            remaining_after=p.get("remaining_after", ""),
            rule_ids=tuple(p.get("rule_ids", [])),
        )
        for p in dep.get("plan", [])
    )
    graph = DependencyGraph(
        nodes=tuple(
            Recommendation(
                finding_id=n["finding_id"],
                rule_id=n["rule_id"],
                action=n["action"],
                owner=n["owner"],
            )
            for n in dep.get("nodes", [])
        ),
        edges=tuple(
            RecEdge(
                src=e["src"],
                dst=e["dst"],
                relation=e["relation"],
                reason=e["reason"],
                src_rule=e.get("src_rule", ""),
                dst_rule=e.get("dst_rule", ""),
            )
            for e in dep.get("edges", [])
        ),
        roadmap=tuple(
            Recommendation(
                finding_id=n["finding_id"],
                rule_id=n["rule_id"],
                action=n["action"],
                owner=n["owner"],
            )
            for n in dep.get("roadmap", [])
        ),
        cycles=tuple(tuple(c) for c in dep.get("cycles", [])),
        plan=plan,
    )
    meta = data["meta"]
    return AuditCls(
        meta=RunMeta(
            tool_version=meta["tool_version"],
            schema_version=meta["schema_version"],
            config_hash=meta["config_hash"],
        ),
        findings=findings,
        inventory=PromptSurfaceInventory(rows=inv_rows),
        dependency_graph=graph,
        guidance=tuple(data.get("guidance") or data.get("documentation") or []),
    )


def _finding_from_dict(d: dict) -> Finding:
    evidence = tuple(
        Evidence(
            path=e["path"],
            span=tuple(e["span"]) if e.get("span") else None,
            excerpt=e["excerpt"],
        )
        for e in d.get("evidence", [])
    )
    return Finding(
        id=d["id"],
        rule_id=d["rule_id"],
        title=d["title"],
        category=d["category"],
        priority=d["priority"],
        verification=d["verification"],
        observability=d["observability"],
        confidence=d["confidence"],
        ownership=d["ownership"],
        evidence=evidence,
        explanation=d["explanation"],
        recommendation=d["recommendation"],
        related=tuple(d.get("related", [])),
        patchable=bool(d.get("patchable", False)),
    )
