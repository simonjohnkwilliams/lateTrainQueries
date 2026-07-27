"""STYLE pack — instruction file used as worklog."""
from __future__ import annotations

from typing import Iterable

from psa.core.config import ConfigView
from psa.core.ids import finding_id
from psa.findings import Finding
from psa.model.types import Evidence, PromptModel


def check_style001(model: PromptModel, _config: ConfigView) -> Iterable[Finding]:
    by_path: dict[str, list] = {}
    for seg in model.segments:
        path = seg.provenance.path
        if path.endswith((".md", ".mdc")):
            by_path.setdefault(path, []).append(seg)

    findings: list[Finding] = []
    for path, segs in sorted(by_path.items()):
        upper = path.upper()
        if not (upper.endswith("AGENTS.MD") or upper.endswith("CLAUDE.MD") or upper.endswith("CLAUDE.LOCAL.MD")):
            continue
        worklogish = sum(1 for s in segs if s.is_worklog or s.is_prefix_poison)
        if worklogish >= 2 and len(segs) >= 3:
            excerpt = "worklog/decision narrative dominates instruction file"
            fid = finding_id(
                rule_id="STYLE001",
                path=path,
                anchor=("document",),
                excerpt=excerpt,
            )
            findings.append(
                Finding(
                    id=fid,
                    rule_id="STYLE001",
                    title="Instruction file used as running worklog",
                    category="STYLE",
                    priority="High value",
                    verification="confirmed",
                    observability="observable",
                    confidence="high",
                    ownership="user",
                    evidence=(Evidence(path=path, span=None, excerpt=excerpt),),
                    explanation=(
                        "Session narrative and debugging history are volatile and erode "
                        "the stable prefix and maintainability of the instruction file."
                    ),
                    recommendation=(
                        "Split durable guidance from the volatile worklog; keep dynamic "
                        "status near the end or in a separate notes file."
                    ),
                    patchable=False,
                )
            )
    return findings
