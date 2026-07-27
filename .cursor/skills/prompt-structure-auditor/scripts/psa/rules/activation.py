"""ACTIVATION pack — dormant / missing frontmatter Cursor rules."""
from __future__ import annotations

import re
from typing import Iterable

import yaml

from psa.core.config import ConfigView
from psa.core.ids import finding_id
from psa.findings import Finding
from psa.model.types import Evidence, PromptModel


def _frontmatter_and_body(text: str) -> tuple[dict | None, bool]:
    """Return (parsed_fm_or_None, has_opening_fence)."""
    if not text.startswith("---"):
        return None, False
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, True
    raw = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, True


def check_act001(model: PromptModel, _config: ConfigView) -> Iterable[Finding]:
    # Operate on unique .mdc paths from segments
    paths = sorted({s.provenance.path for s in model.segments if s.provenance.path.endswith(".mdc")})
    # Need raw text — recover from segment evidence/source by re-reading via joined segment texts
    # Better: load from first segment's file by reconstructing from model isn't enough.
    # Use segment frontmatter text stored in (frontmatter) segments.
    findings: list[Finding] = []
    by_path: dict[str, list] = {}
    for seg in model.segments:
        if seg.provenance.path.endswith(".mdc"):
            by_path.setdefault(seg.provenance.path, []).append(seg)

    for path, segs in sorted(by_path.items()):
        fm_seg = next((s for s in segs if s.provenance.anchor == ("(frontmatter)",)), None)
        body_seg = next((s for s in segs if s.provenance.anchor == ("(rule body)",)), None)
        if fm_seg is None:
            continue  # handled by ACT002
        try:
            data = yaml.safe_load(fm_seg.text) or {}
        except yaml.YAMLError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        always = data.get("alwaysApply", None)
        description = data.get("description")
        globs = data.get("globs")
        if always is False and not description and not globs:
            excerpt = "alwaysApply: false"
            fid = finding_id(
                rule_id="ACT001",
                path=path,
                anchor=("alwaysApply",),
                excerpt=excerpt,
            )
            findings.append(
                Finding(
                    id=fid,
                    rule_id="ACT001",
                    title="Dormant Cursor rule: no description or globs",
                    category="ACTIVATION",
                    priority="High value",
                    verification="confirmed",
                    observability="observable",
                    confidence="high",
                    ownership="user",
                    evidence=(Evidence(path=path, span=fm_seg.provenance.span, excerpt=excerpt),),
                    explanation=(
                        "A rule with alwaysApply:false and neither description nor globs "
                        "has no trigger the agent can match, so it is effectively dormant."
                    ),
                    recommendation=(
                        "Add a description and/or globs, or set alwaysApply:true for "
                        "rules meant to apply constantly."
                    ),
                    patchable=True,
                )
            )
    return findings


def check_act002(model: PromptModel, _config: ConfigView) -> Iterable[Finding]:
    findings: list[Finding] = []
    by_path: dict[str, list] = {}
    for seg in model.segments:
        if seg.provenance.path.endswith(".mdc"):
            by_path.setdefault(seg.provenance.path, []).append(seg)

    for path, segs in sorted(by_path.items()):
        fm_seg = next((s for s in segs if s.provenance.anchor == ("(frontmatter)",)), None)
        if fm_seg is not None:
            continue
        # No frontmatter segment → missing metadata
        body = segs[0]
        excerpt = "(missing YAML frontmatter)"
        fid = finding_id(
            rule_id="ACT002",
            path=path,
            anchor=("frontmatter",),
            excerpt=excerpt,
        )
        findings.append(
            Finding(
                id=fid,
                rule_id="ACT002",
                title="Cursor rule missing activation frontmatter",
                category="ACTIVATION",
                priority="High value",
                verification="confirmed",
                observability="observable",
                confidence="high",
                ownership="user",
                evidence=(Evidence(path=path, span=body.provenance.span, excerpt=excerpt),),
                explanation=(
                    "Without YAML frontmatter, activation scope (alwaysApply / description / globs) "
                    "is undefined."
                ),
                recommendation="Add YAML frontmatter with alwaysApply and/or description/globs.",
                patchable=True,
            )
        )
    return findings
