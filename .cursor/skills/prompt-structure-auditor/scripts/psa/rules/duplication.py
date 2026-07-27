"""DUPLICATION pack — repeated instructions across sections/sources."""
from __future__ import annotations

import re
from typing import Iterable

from psa.core.config import ConfigView
from psa.core.ids import finding_id
from psa.findings import Finding
from psa.model.types import Evidence, PromptModel


def _normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def check_dup001(model: PromptModel, _config: ConfigView) -> Iterable[Finding]:
    findings: list[Finding] = []

    # Exact phrase duplication
    phrases = [
        "redirect uri",
        "client_id and client_secret",
        "copy client_id",
        "implement only the requested story",
        "only implement one story at a time",
    ]

    # Related architecture-freeze family (validation dry-run VR2)
    arch_family = (
        "architecture is frozen",
        "do not redesign the architecture",
        "do not redesign architecture",
    )

    for phrase in phrases:
        hits: list[tuple[str, tuple[int, int] | None, str]] = []
        for seg in model.segments:
            blob = _normalize(" ".join(seg.provenance.anchor) + " " + seg.text)
            if phrase in blob:
                hits.append((seg.provenance.path, seg.provenance.span, phrase))
        unique_locs = {(h[0], h[1]) for h in hits}
        if len(unique_locs) >= 2:
            path = hits[0][0]
            excerpt = phrase
            fid = finding_id(
                rule_id="DUP001",
                path=path,
                anchor=(phrase,),
                excerpt=excerpt,
            )
            evidence = tuple(
                Evidence(path=p, span=sp, excerpt=phrase) for p, sp, _ in hits[:4]
            )
            findings.append(
                Finding(
                    id=fid,
                    rule_id="DUP001",
                    title=f'Duplicated instruction: "{phrase}"',
                    category="DUPLICATION",
                    priority="Medium value",
                    verification="confirmed",
                    observability="observable",
                    confidence="high",
                    ownership="user",
                    evidence=evidence,
                    explanation=(
                        "The same instruction or setup step appears in multiple places, "
                        "which risks drift and contradiction over time."
                    ),
                    recommendation="Consolidate into one owner section and reference it elsewhere.",
                    patchable=False,
                )
            )

    # Architecture freeze restated across files/sections
    arch_hits: list[tuple[str, tuple[int, int] | None, str]] = []
    for seg in model.segments:
        blob = _normalize(" ".join(seg.provenance.anchor) + " " + seg.text)
        for phrase in arch_family:
            if phrase in blob:
                arch_hits.append((seg.provenance.path, seg.provenance.span, phrase))
                break
    if len({(h[0], h[1]) for h in arch_hits}) >= 2:
        path = arch_hits[0][0]
        excerpt = "architecture freeze / do not redesign"
        fid = finding_id(
            rule_id="DUP001",
            path=path,
            anchor=("architecture-freeze",),
            excerpt=excerpt,
        )
        findings.append(
            Finding(
                id=fid,
                rule_id="DUP001",
                title='Duplicated instruction: architecture freeze / do not redesign',
                category="DUPLICATION",
                priority="Medium value",
                verification="confirmed",
                observability="observable",
                confidence="high",
                ownership="user",
                evidence=tuple(
                    Evidence(path=p, span=sp, excerpt=ph) for p, sp, ph in arch_hits[:4]
                ),
                explanation=(
                    "The architecture-freeze guardrail is restated across sources, "
                    "which risks drift."
                ),
                recommendation=(
                    "State the freeze once in an always-applied rule; reference it elsewhere."
                ),
                patchable=False,
            )
        )

    # One-story family across files
    story_family = (
        "implement only the requested story",
        "only implement one story at a time",
    )
    story_hits: list[tuple[str, tuple[int, int] | None, str]] = []
    for seg in model.segments:
        blob = _normalize(" ".join(seg.provenance.anchor) + " " + seg.text)
        for phrase in story_family:
            if phrase in blob:
                story_hits.append((seg.provenance.path, seg.provenance.span, phrase))
                break
    if len({(h[0], h[1]) for h in story_hits}) >= 2:
        path = story_hits[0][0]
        excerpt = "one story at a time"
        fid = finding_id(
            rule_id="DUP001",
            path=path,
            anchor=("one-story",),
            excerpt=excerpt,
        )
        findings.append(
            Finding(
                id=fid,
                rule_id="DUP001",
                title='Duplicated instruction: "one story at a time"',
                category="DUPLICATION",
                priority="Medium value",
                verification="confirmed",
                observability="observable",
                confidence="high",
                ownership="user",
                evidence=tuple(
                    Evidence(path=p, span=sp, excerpt=ph) for p, sp, ph in story_hits[:4]
                ),
                explanation="The one-story rule is restated in multiple rule files.",
                recommendation="Consolidate to a single owner rule.",
                patchable=False,
            )
        )

    return findings

