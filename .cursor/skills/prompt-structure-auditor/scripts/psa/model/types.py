"""Immutable Prompt Model types (RFC §6)."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Evidence:
    path: str
    span: tuple[int, int] | None
    excerpt: str

    def to_dict(self) -> dict:
        return {"path": self.path, "span": list(self.span) if self.span else None, "excerpt": self.excerpt}


@dataclass(frozen=True)
class Provenance:
    source_id: str
    path: str
    span: tuple[int, int] | None
    anchor: tuple[str, ...]


@dataclass(frozen=True)
class Segment:
    id: str
    provenance: Provenance
    order: int
    content_kind: str
    stability: str
    volatility_signals: tuple[Evidence, ...]
    ownership: str
    relocatability: str
    confidence: str
    evidence: tuple[Evidence, ...]
    text: str = ""
    is_prefix_poison: bool = False
    is_worklog: bool = False


@dataclass(frozen=True)
class Edge:
    kind: str
    src: str
    dst: str
    observability: str
    confidence: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class PromptModel:
    segments: tuple[Segment, ...]
    edges: tuple[Edge, ...]
    _by_id: Mapping[str, Segment]
    _out: Mapping[str, tuple[Edge, ...]]
    _in: Mapping[str, tuple[Edge, ...]]

    def get(self, seg_id: str) -> Segment:
        return self._by_id[seg_id]

    def out(self, seg_id: str) -> tuple[Edge, ...]:
        return self._out.get(seg_id, ())

    def in_(self, seg_id: str) -> tuple[Edge, ...]:
        return self._in.get(seg_id, ())


def make_model(segments: tuple[Segment, ...], edges: tuple[Edge, ...]) -> PromptModel:
    by_id = MappingProxyType({s.id: s for s in segments})
    out: dict[str, list[Edge]] = {}
    inn: dict[str, list[Edge]] = {}
    for e in edges:
        out.setdefault(e.src, []).append(e)
        inn.setdefault(e.dst, []).append(e)
    return PromptModel(
        segments=segments,
        edges=edges,
        _by_id=by_id,
        _out=MappingProxyType({k: tuple(v) for k, v in out.items()}),
        _in=MappingProxyType({k: tuple(v) for k, v in inn.items()}),
    )
