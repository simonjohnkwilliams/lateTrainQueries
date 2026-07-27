"""Build immutable Prompt Model from discovered sources."""
from __future__ import annotations

import re

from psa.core.ids import segment_id
from psa.discovery import Source
from psa.model.classify import classify_section
from psa.model.types import Edge, Evidence, Provenance, Segment, make_model


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _split_markdown_sections(text: str) -> list[tuple[str, str, int, int]]:
    """Return list of (heading, body, start_line, end_line) 1-based."""
    lines = text.splitlines()
    if not lines:
        return []
    indices: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            indices.append((i, m.group(2).strip()))
    if not indices:
        return [("(document)", text, 1, len(lines))]

    sections: list[tuple[str, str, int, int]] = []
    # preamble before first heading
    if indices[0][0] > 0:
        pre = "\n".join(lines[: indices[0][0]])
        sections.append(("(preamble)", pre, 1, indices[0][0]))

    for idx, (start, heading) in enumerate(indices):
        end = indices[idx + 1][0] if idx + 1 < len(indices) else len(lines)
        body = "\n".join(lines[start + 1 : end])
        sections.append((heading, body, start + 1, end))
    return sections


def _split_mdc(text: str) -> list[tuple[str, str, int, int]]:
    """Cursor rule: optional frontmatter + body as one instruction segment."""
    lines = text.splitlines()
    if text.startswith("---"):
        # find closing ---
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            fm = "\n".join(lines[1:end])
            body = "\n".join(lines[end + 1 :])
            return [
                ("(frontmatter)", fm, 1, end + 1),
                ("(rule body)", body, end + 2, len(lines)),
            ]
    return [("(rule body)", text, 1, max(1, len(lines)))]


def build_model(sources: tuple[Source, ...]):
    segments: list[Segment] = []
    edges: list[Edge] = []
    order = 0

    for src in sources:
        if src.subtype != "instruction" or not src.text:
            continue
        path = src.path.replace("\\", "/")
        if path.endswith(".mdc"):
            parts = _split_mdc(src.text)
        else:
            parts = _split_markdown_sections(src.text)

        local_ids: list[str] = []
        for heading, body, start, end in parts:
            # Skip empty frontmatter-only noise for ordering rules? keep all.
            clf = classify_section(heading, body)
            anchor = (heading,)
            sid = segment_id(path=path, anchor=anchor, order=order, kind=clf.content_kind)
            vol_ev = tuple(
                Evidence(path=path, span=(start, end), excerpt=sig[:120])
                for sig in clf.volatility_signals
            )
            seg = Segment(
                id=sid,
                provenance=Provenance(
                    source_id=src.source_id,
                    path=path,
                    span=(start, end),
                    anchor=anchor,
                ),
                order=order,
                content_kind=clf.content_kind,
                stability=clf.stability,
                volatility_signals=vol_ev,
                ownership=src.default_ownership,
                relocatability="movable-within-source",
                confidence=clf.confidence,
                evidence=(Evidence(path=path, span=(start, end), excerpt=(heading + "\n" + body)[:160]),),
                text=body if body else heading,
                is_prefix_poison=clf.is_prefix_poison,
                is_worklog=clf.is_worklog,
            )
            segments.append(seg)
            local_ids.append(sid)
            order += 1

        for a, b in zip(local_ids, local_ids[1:]):
            edges.append(
                Edge(
                    kind="precedes",
                    src=a,
                    dst=b,
                    observability="observable",
                    confidence="high",
                    evidence=(),
                )
            )
            # governs: frontmatter -> body
            sa = next(s for s in segments if s.id == a)
            if sa.provenance.anchor == ("(frontmatter)",):
                edges.append(
                    Edge(
                        kind="governs",
                        src=a,
                        dst=b,
                        observability="observable",
                        confidence="high",
                        evidence=(),
                    )
                )

    segs = tuple(segments)
    eds = tuple(sorted(edges, key=lambda e: (e.kind, e.src, e.dst)))
    return make_model(segs, eds)
