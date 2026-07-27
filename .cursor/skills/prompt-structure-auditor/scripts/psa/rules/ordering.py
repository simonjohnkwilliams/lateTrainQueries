"""ORDERING pack — ORDER001 early prefix-poisoning volatility."""
from __future__ import annotations

from typing import Iterable

from psa.core.config import ConfigView
from psa.core.ids import finding_id
from psa.findings import Finding
from psa.model.types import Evidence, PromptModel, Segment


def check_order001(model: PromptModel, _config: ConfigView) -> Iterable[Finding]:
    """Raise when a *prefix-poison* volatile segment appears before later stable content.

    Worklog headings (On Hold, Debugging, Known Issue) are intentionally ignored
    here — they are STYLE001 concerns, not ORDER001.
    """
    by_path: dict[str, list[Segment]] = {}
    for seg in model.segments:
        by_path.setdefault(seg.provenance.path, []).append(seg)

    findings: list[Finding] = []
    for path, segs in sorted(by_path.items()):
        segs = sorted(segs, key=lambda s: s.order)
        for i, seg in enumerate(segs):
            if not seg.is_prefix_poison:
                continue
            if seg.stability not in {"volatile", "mixed"}:
                continue
            anchor = seg.provenance.anchor[0] if seg.provenance.anchor else ""
            if anchor in {"(frontmatter)", "(preamble)", "(rule body)"}:
                continue
            later_stable = [
                s
                for s in segs[i + 1 :]
                if s.stability == "stable" and not s.is_worklog
            ]
            if not later_stable:
                continue
            stable = later_stable[0]
            excerpt = anchor
            fid = finding_id(
                rule_id="ORDER001",
                path=path,
                anchor=seg.provenance.anchor,
                excerpt=excerpt,
            )
            findings.append(
                Finding(
                    id=fid,
                    rule_id="ORDER001",
                    title=f'Volatile "{anchor}" appears before stable content',
                    category="ORDERING",
                    priority="High value",
                    verification="confirmed",
                    observability="observable",
                    confidence="high",
                    ownership=seg.ownership,
                    evidence=(
                        Evidence(
                            path=path,
                            span=seg.provenance.span,
                            excerpt=anchor,
                        ),
                        Evidence(
                            path=path,
                            span=stable.provenance.span,
                            excerpt=stable.provenance.anchor[0] if stable.provenance.anchor else "",
                        ),
                    ),
                    explanation=(
                        "Content before the first change is what a prompt cache can reuse. "
                        "Placing session-dynamic content ahead of stable material puts the "
                        "stable sections behind a frequent change point."
                    ),
                    recommendation=(
                        f'Move "{anchor}" below stable sections (e.g. '
                        f'"{stable.provenance.anchor[0] if stable.provenance.anchor else "standards"}"); '
                        "group dynamic values near the end of the file."
                    ),
                    patchable=True,
                )
            )
    return findings
